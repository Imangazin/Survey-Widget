import requests
from requests.auth import HTTPBasicAuth
import os
from logger_config import logger
import dotenv
import mysql.connector
import json
import urllib.parse


dotenv_file = dotenv.find_dotenv()
dotenv.load_dotenv(dotenv_file)

def trade_in_refresh_token(config):
    try:
        response = requests.post(
            'https://auth.brightspace.com/core/connect/token',
            data={
                'grant_type': 'refresh_token',
                'refresh_token': config['refresh_token'],
                'scope': config['scope']
            },
            auth=HTTPBasicAuth(config['client_id'], config['client_secret'])
        )
        response.raise_for_status()
        response_data = response.json()
        return response_data
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during token refresh: {e}")
        return None
    except KeyError:
        logger.error("Error: Unexpected response format.")
        return None

def get_config():
    return {
        "client_id": os.environ["client_id"],
        "client_secret": os.environ["client_secret"],
        "refresh_token": os.environ["refresh_token"],
        "scope": os.environ["scope"],
        "bspace_url": os.environ["bspace_url"],
        "host": os.environ["host"],
        "user": os.environ["user"],
        "password": os.environ["password"],
        "database": os.environ["database"],
        "widgetId": os.environ["widgetId"],
        "orgUnitId": os.environ["orgUnitId"],
    }

def set_refresh_token(refresh_token):
    os.environ["refresh_token"] = refresh_token
    dotenv.set_key(dotenv_file, "refresh_token", os.environ["refresh_token"])
    dotenv.load_dotenv(dotenv_file)

def get_with_auth(endpoint, access_token):
    try:
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(endpoint, headers=headers)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"GET {endpoint} failed: {e}")
        return None


def put_with_auth(endpoint, access_token, data):
    try:
        headers = {'Authorization': f'Bearer {access_token}', 'Content-Type':'application/json'}
        response = requests.put(endpoint, headers=headers, json=data)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        status = getattr(locals().get("response", None), "status_code", "No Status")
        text = getattr(locals().get("response", None), "text", "")
        logger.error(f"PUT {endpoint} failed. Status: {status}. {text if text else e}")
        return None

def resolve_user_id(access_token, bspace_url, student_username):
    """
    Given a studentId (used as username in Brightspace), resolves the Brightspace UserId.
    Returns integer UserId or None.
    """
    encoded_username = urllib.parse.quote(str(student_username))
    endpoint = f"{bspace_url}/d2l/api/lp/1.46/users/?userName={encoded_username}"

    response = get_with_auth(endpoint, access_token)
    if not response:
        logger.error(f"Failed to resolve Brightspace UserId for username {student_username}: No response")
        return None

    try:
        data = response.json()
        return data.get("UserId")
    except Exception as e:
        logger.error(f"Error parsing Brightspace user lookup for username {student_username}: {e}")
        return None


# --- Database and widget functions ---

def fetch_data_from_db(config, query, params=None):
    """
    Connects to MariaDB and fetches all rows from surveys table where isSent = 0.
    Returns a list of dicts.
    """
    try:
        conn = mysql.connector.connect(
            host=config["host"],
            user=config["user"],
            password=config["password"],
            database=config["database"]
        )
        cur = conn.cursor(dictionary=True)
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except mysql.connector.Error as e:
        logger.error(f"Database error: {e}")
        return []

def update_records_as_sent(config, query, params=None):
    """
    Executes UPDATE queries to mark surveys or survey_assignments as sent.
    """
    try:
        conn = mysql.connector.connect(
            host=config["host"],
            user=config["user"],
            password=config["password"],
            database=config["database"]
        )
        cur = conn.cursor()
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        conn.commit()
        cur.close()
        conn.close()
    except mysql.connector.Error as e:
        logger.error(f"Database update error: {e}")


def widget_data_push(access_token, config):

    widget_success = 0
    widget_error = 0

    # Fetch all active surveys (startDate <= NOW() <= endDate) regardless of isSent.
    active_surveys = """
        SELECT surveyId, name, description, startDate, endDate, surveyType
        FROM surveys
        WHERE startDate <= NOW()
          AND endDate >= NOW();
    """
    rows = fetch_data_from_db(config, active_surveys)

    items = []
    for r in rows:
        items.append({
            "surveyId": r["surveyId"],
            "name": r["name"],
            "description": r["description"],
            "startDate": str(r["startDate"]),
            "endDate": str(r["endDate"]),
            "surveyType": r["surveyType"]
        })

    inner = json.dumps({"Items": items})
    payload = {"Data": inner}

    if not items:
        logger.info("No surveys to push (both new and active).")
        return None

    endpoint = f"{config['bspace_url']}/d2l/api/lp/1.46/{config['orgUnitId']}/widgetdata/{config['widgetId']}"
    response = put_with_auth(endpoint, access_token, payload)
    if response and response.status_code in (200, 201, 204):
        logger.info(f"Custom Widget Data push succeeded. Sent {len(items)} surveys.")
        update_query = "UPDATE surveys SET isSent = 1 WHERE surveyId = %s;"
        for r in rows:
            update_records_as_sent(config, update_query, (r["surveyId"],))
        widget_success = len(items)
    else:
        logger.error(f"Custom Widget Data push failed. Status: {response.status_code if response else 'No Response'}")
        widget_error = len(items)

    return {"widget_success": widget_success, "widget_error": widget_error}


def user_data_push(access_token, config):
    user_success = 0
    user_error = 0

    # 1) Students with NEW (unsent) survey links
    new_students_q = """
        SELECT DISTINCT studentId
        FROM survey_assignments
        WHERE isSent = 0;
    """
    new_students = fetch_data_from_db(config, new_students_q)

    # 2) Students with EXPIRED surveys already sent (isSent=1 but survey endDate < NOW)
    expired_students_q = """
        SELECT DISTINCT sa.studentId
        FROM survey_assignments sa
        JOIN surveys s ON sa.surveyId = s.surveyId
        WHERE sa.isSent = 1
          AND s.endDate < NOW();
    """
    expired_students = fetch_data_from_db(config, expired_students_q)

    # Union of studentIds needing an update (new assignments OR expired clean-up)
    student_ids = set()
    for r in new_students:
        student_ids.add(r["studentId"])
    for r in expired_students:
        student_ids.add(r["studentId"])

    if not student_ids:
        logger.info("No user-specific updates needed (no new surveys and no expirations).")
        return {"user_success": user_success, "user_error": user_error}

    # For each affected student, push ONLY the ACTIVE surveys (this removes expirations)
    for student_id in student_ids:

        # Fetch all ACTIVE survey links for this student (include both sent and unsent assignments)
        active_links_q = """
            SELECT sa.surveyId, sa.surveyLink
            FROM survey_assignments sa
            JOIN surveys s ON sa.surveyId = s.surveyId
            WHERE sa.studentId = %s
              AND s.startDate <= NOW()
              AND s.endDate >= NOW();
        """
        active_rows = fetch_data_from_db(config, active_links_q, (student_id,))

        items = []
        for a in active_rows:
            items.append({
                "surveyId": a["surveyId"],
                "url": a["surveyLink"]
            })

        # Build Brightspace double-encoded payload
        inner = json.dumps({"Items": items})
        payload = {"Data": inner}

        # Resolve Brightspace UserId from username/studentId
        userId = resolve_user_id(access_token, config["bspace_url"], student_id)
        if not userId:
            logger.error(f"Skipping student {student_id} — could not resolve Brightspace UserId.")
            user_error += 1
            continue

        endpoint = f"{config['bspace_url']}/d2l/api/lp/1.46/{config['orgUnitId']}/widgetdata/{config['widgetId']}/{userId}"
        response = put_with_auth(endpoint, access_token, payload)

        if response and response.status_code in (200, 201, 204):
            logger.info(f"User-Specific widget push SUCCESS for student {student_id}. Active items: {len(items)}")
            user_success += 1

            # Mark newly sent assignments as sent (isSent=0 -> 1) for this student.
            # This does not change expired rows; it just acknowledges new ones were pushed.
            update_new_q = """
                UPDATE survey_assignments
                SET isSent = 1
                WHERE studentId = %s
                  AND isSent = 0;
            """
            update_records_as_sent(config, update_new_q, (student_id,))

            # Mark expired previously-sent assignments as cleaned so they don't trigger cleanup every day
            mark_expired_q = """
                UPDATE survey_assignments sa
                JOIN surveys s ON sa.surveyId = s.surveyId
                SET sa.isSent = 2
                WHERE sa.studentId = %s
                  AND sa.isSent = 1
                  AND s.endDate < NOW();
            """
            update_records_as_sent(config, mark_expired_q, (student_id,))
        else:
            logger.error(f"User-Specific widget push FAILED for student {student_id}. Status: {response.status_code if response else 'No Response'}")
            user_error += 1

    return {"user_success": user_success, "user_error": user_error}

if __name__ == "__main__":
    logger.info("=== Survey Widget Run Started ===")
    try:
        config = get_config()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise SystemExit(1)

    try:
        token_response = trade_in_refresh_token(config)
        if not token_response:
            logger.error("Token refresh failed. Exiting.")
            raise SystemExit(1)

        new_refresh = token_response.get("refresh_token")
        access_token = token_response.get("access_token")

        if not new_refresh or not access_token:
            logger.error("Token refresh response missing refresh_token or access_token.")
            raise SystemExit(1)

        # Update refresh token in .env
        try:
            set_refresh_token(new_refresh)
            logger.info("Refresh token updated in .env successfully.")
        except Exception as e:
            logger.error(f"Failed to update refresh token in .env: {e}")
            raise SystemExit(1)

        # Push widget (course-level) data
        widget_result = widget_data_push(access_token, config)

        # Push user-specific widget data
        user_result = user_data_push(access_token, config)

        if widget_result:
            logger.info(f"Widget Data Summary: {widget_result['widget_success']} pushed, {widget_result['widget_error']} errors.")
        if user_result:
            logger.info(f"User Data Summary: {user_result['user_success']} pushed, {user_result['user_error']} errors.")

        logger.info("=== Survey Widget Run Completed ===")

    except Exception as e:
        logger.error(f"Fatal error during main execution: {e}")
        raise SystemExit(1)
