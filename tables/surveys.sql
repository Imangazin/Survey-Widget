CREATE TABLE surveys (
    surveyId INT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    startDate DATE,
    endDate DATE,
    isSent TINYINT(1) DEFAULT 0,
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE survey_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    studentId VARCHAR(50) NOT NULL,
    surveyId INT NOT NULL,
    surveyLink VARCHAR(500) NOT NULL,  -- Unique link for this user
    isSent TINYINT(1) DEFAULT 0,       -- Flag for API 2 push
    isCompleted TINYINT(1) DEFAULT 0,  -- Completion flag
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updatedAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_survey
        FOREIGN KEY (surveyId) REFERENCES surveys(surveyId)
        ON DELETE CASCADE
);