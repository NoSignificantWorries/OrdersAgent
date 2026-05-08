package api

import (
	"context"
	"database/sql"
	"time"
)

type QueueItem struct {
	ID             int64      `json:"id"`
	AssignedTo     *int64     `json:"assigned_to,omitempty"`
	TargetUserID   int64      `json:"target_user_id"`
	Subject        string     `json:"email_subject"`
	Body           string     `json:"email_body"`
	EmailUID       *int64     `json:"email_uid,omitempty"`
	EmailFrom      *string    `json:"email_from,omitempty"`
	EmailDate      *time.Time `json:"email_date,omitempty"`
	DocName        *string    `json:"document_name,omitempty"`
	ObjectBucket   *string    `json:"object_bucket,omitempty"`
	ObjectKey      *string    `json:"object_key,omitempty"`
	Status         string     `json:"status"`
	CreatedAt      string     `json:"created_at"`
	Prob1          *float64   `json:"prob_1,omitempty"`
	PredictedClass *int16     `json:"predicted_class,omitempty"`
	ModelDecision  *string    `json:"model_decision,omitempty"`
}

type EmailGroup struct {
	EmailUID     int64  `json:"email_uid"`
	TargetUserID int64  `json:"target_user_id"`
	Subject      string `json:"email_subject"`
	Body         string `json:"email_body"`
	FilesText    string `json:"files_text"`
}

// Вставка записи в очередь
func (db *DB) InsertQueueItem(ctx context.Context, item QueueItem) (int64, error) {
	const q = `
        INSERT INTO process_queue (
            assigned_to,
            target_user_id,
            email_subject,
            email_body,
            email_uid,
            email_from,
            email_date,
            document_name,
            object_bucket,
            object_key,
            status
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        RETURNING id
    `

	var assignedTo any
	if item.AssignedTo != nil {
		assignedTo = *item.AssignedTo
	} else {
		assignedTo = nil
	}

	var emailUID any
	if item.EmailUID != nil {
		emailUID = *item.EmailUID
	} else {
		emailUID = nil
	}

	var docName any
	if item.DocName != nil {
		docName = *item.DocName
	} else {
		docName = nil
	}

	var objectBucket any
	if item.ObjectBucket != nil {
		objectBucket = *item.ObjectBucket
	} else {
		objectBucket = nil
	}

	var objectKey any
	if item.ObjectKey != nil {
		objectKey = *item.ObjectKey
	} else {
		objectKey = nil
	}

	var id int64
	err := db.Conn.QueryRowContext(
		ctx, q,
		assignedTo,
		item.TargetUserID,
		item.Subject,
		item.Body,
		emailUID,
		item.EmailFrom,
		item.EmailDate,
		docName,
		objectBucket,
		objectKey,
		item.Status,
	).Scan(&id)
	if err != nil {
		return 0, err
	}

	return id, nil
}

// Чтение очереди
func (db *DB) ListQueue(ctx context.Context, status string, limit int) ([]QueueItem, error) {
	const q = `
        SELECT id, assigned_to, email_subject, email_body,
               document_name, status, created_at,
               prob_1, predicted_class, model_decision
        FROM process_queue
        WHERE ($1 = '' OR status = $1)
        ORDER BY created_at DESC
        LIMIT $2
    `
	rows, err := db.Conn.QueryContext(ctx, q, status, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var res []QueueItem

	for rows.Next() {
		var it QueueItem
		var assignedTo sql.NullInt64
		var docName sql.NullString
		var prob1 sql.NullFloat64
		var predClass sql.NullInt16
		var modelDecision sql.NullString
		var emailBody sql.NullString

		if err := rows.Scan(
			&it.ID,
			&assignedTo,
			&it.Subject,
			&emailBody,
			&docName,
			&it.Status,
			&it.CreatedAt,
			&prob1,
			&predClass,
			&modelDecision,
		); err != nil {
			return nil, err
		}

		if emailBody.Valid {
			it.Body = emailBody.String
		} else {
			it.Body = ""
		}

		if assignedTo.Valid {
			v := assignedTo.Int64
			it.AssignedTo = &v
		}

		if docName.Valid {
			v := docName.String
			it.DocName = &v
		}

		if prob1.Valid {
			v := prob1.Float64
			it.Prob1 = &v
		}

		if predClass.Valid {
			v := predClass.Int16
			it.PredictedClass = &v
		}

		if modelDecision.Valid {
			v := modelDecision.String
			it.ModelDecision = &v
		}

		res = append(res, it)
	}

	return res, rows.Err()
}

// GetQueueItemByID — получить одну запись из process_queue по id
func (db *DB) GetQueueItemByID(ctx context.Context, id int64) (QueueItem, error) {
	const q = `
        SELECT
            id,
            assigned_to,
            target_user_id,
            email_subject,
            email_body,
            email_uid,
            email_from,
            email_date,
            document_name,
            object_bucket,
            object_key,
            status,
            created_at,
            prob_1,
            predicted_class,
            model_decision
        FROM process_queue
        WHERE id = $1
    `
	var it QueueItem

	var assignedTo sql.NullInt64
	var emailUID sql.NullInt64
	var emailFrom sql.NullString
	var emailDate sql.NullTime
	var docName sql.NullString
	var objectBucket sql.NullString
	var objectKey sql.NullString
	var prob1 sql.NullFloat64
	var predClass sql.NullInt16
	var modelDecision sql.NullString
	var emailBody sql.NullString

	err := db.Conn.QueryRowContext(ctx, q, id).Scan(
		&it.ID,
		&assignedTo,
		&it.TargetUserID,
		&it.Subject,
		&emailBody,
		&emailUID,
		&emailFrom,
		&emailDate,
		&docName,
		&objectBucket,
		&objectKey,
		&it.Status,
		&it.CreatedAt,
		&prob1,
		&predClass,
		&modelDecision,
	)
	if err != nil {
		return QueueItem{}, err
	}

	if emailBody.Valid {
		it.Body = emailBody.String
	} else {
		it.Body = ""
	}
	if assignedTo.Valid {
		v := assignedTo.Int64
		it.AssignedTo = &v
	}
	if emailUID.Valid {
		v := emailUID.Int64
		it.EmailUID = &v
	}
	if emailFrom.Valid {
		v := emailFrom.String
		it.EmailFrom = &v
	}
	if emailDate.Valid {
		t := emailDate.Time
		it.EmailDate = &t
	}
	if docName.Valid {
		v := docName.String
		it.DocName = &v
	}
	if objectBucket.Valid {
		v := objectBucket.String
		it.ObjectBucket = &v
	}
	if objectKey.Valid {
		v := objectKey.String
		it.ObjectKey = &v
	}
	if prob1.Valid {
		v := prob1.Float64
		it.Prob1 = &v
	}
	if predClass.Valid {
		v := predClass.Int16
		it.PredictedClass = &v
	}
	if modelDecision.Valid {
		v := modelDecision.String
		it.ModelDecision = &v
	}

	return it, nil
}

// UpdateQueueItemStatus — обновить статус записи в очереди по id
func (db *DB) UpdateQueueItemStatus(ctx context.Context, id int64, status string) error {
	const q = `
        UPDATE process_queue
        SET status = $1
        WHERE id = $2
    `
	_, err := db.Conn.ExecContext(ctx, q, status, id)
	return err
}

// GetEmailGroupByUID — получить агрегированные данные письма по email_uid
func (db *DB) GetEmailGroupByUID(ctx context.Context, emailUID int64) (EmailGroup, error) {
	const q = `
        SELECT
            email_uid,
            MIN(target_user_id) AS target_user_id,
            COALESCE(MIN(email_subject), '') AS email_subject,
            COALESCE(MIN(email_body), '') AS email_body,
            COALESCE(
                STRING_AGG(
                    file_label,
                    E'\n'
                    ORDER BY file_idx
                ),
                ''
            ) AS files_text
        FROM (
            SELECT
                email_uid,
                target_user_id,
                email_subject,
                email_body,
                document_name,
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY email_uid
                    ORDER BY id
                ) AS file_idx,
                CASE
                    WHEN document_name IS NOT NULL AND document_name <> ''
                        THEN 'FILE_' || ROW_NUMBER() OVER (
                            PARTITION BY email_uid
                            ORDER BY id
                        )::text || ': ' || document_name
                    ELSE NULL
                END AS file_label
            FROM process_queue
            WHERE email_uid = $1
        ) t
        GROUP BY email_uid
    `

	var res EmailGroup
	var body sql.NullString
	var filesText sql.NullString

	err := db.Conn.QueryRowContext(ctx, q, emailUID).Scan(
		&res.EmailUID,
		&res.TargetUserID,
		&res.Subject,
		&body,
		&filesText,
	)
	if err != nil {
		return EmailGroup{}, err
	}

	if body.Valid {
		res.Body = body.String
	} else {
		res.Body = ""
	}

	if filesText.Valid {
		res.FilesText = filesText.String
	} else {
		res.FilesText = ""
	}

	return res, nil
}

// GetEmailFilesByUID — получить все файлы письма по email_uid.
func (db *DB) GetEmailFilesByUID(ctx context.Context, emailUID int64) ([]QueueItem, error) {
	const q = `
		SELECT
			id,
			assigned_to,
			target_user_id,
			email_subject,
			email_body,
			email_uid,
			email_from,
			email_date,
			document_name,
			object_bucket,
			object_key,
			status,
			created_at,
			prob_1,
			predicted_class,
			model_decision
		FROM process_queue
		WHERE email_uid = $1
		ORDER BY id
	`

	rows, err := db.Conn.QueryContext(ctx, q, emailUID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var res []QueueItem

	for rows.Next() {
		var it QueueItem

		var assignedTo sql.NullInt64
		var emailUIDCol sql.NullInt64
		var emailFrom sql.NullString
		var emailDate sql.NullTime
		var docName sql.NullString
		var objectBucket sql.NullString
		var objectKey sql.NullString
		var prob1 sql.NullFloat64
		var predClass sql.NullInt16
		var modelDecision sql.NullString
		var emailBody sql.NullString

		if err := rows.Scan(
			&it.ID,
			&assignedTo,
			&it.TargetUserID,
			&it.Subject,
			&emailBody,
			&emailUIDCol,
			&emailFrom,
			&emailDate,
			&docName,
			&objectBucket,
			&objectKey,
			&it.Status,
			&it.CreatedAt,
			&prob1,
			&predClass,
			&modelDecision,
		); err != nil {
			return nil, err
		}

		if emailBody.Valid {
			it.Body = emailBody.String
		} else {
			it.Body = ""
		}
		if assignedTo.Valid {
			v := assignedTo.Int64
			it.AssignedTo = &v
		}
		if emailUIDCol.Valid {
			v := emailUIDCol.Int64
			it.EmailUID = &v
		}
		if emailFrom.Valid {
			v := emailFrom.String
			it.EmailFrom = &v
		}
		if emailDate.Valid {
			t := emailDate.Time
			it.EmailDate = &t
		}
		if docName.Valid {
			v := docName.String
			it.DocName = &v
		}
		if objectBucket.Valid {
			v := objectBucket.String
			it.ObjectBucket = &v
		}
		if objectKey.Valid {
			v := objectKey.String
			it.ObjectKey = &v
		}
		if prob1.Valid {
			v := prob1.Float64
			it.Prob1 = &v
		}
		if predClass.Valid {
			v := predClass.Int16
			it.PredictedClass = &v
		}
		if modelDecision.Valid {
			v := modelDecision.String
			it.ModelDecision = &v
		}

		res = append(res, it)
	}

	return res, rows.Err()
}

// UpdateQueueStatusByEmailUID — обновить статус всех строк письма по email_uid
func (db *DB) UpdateQueueStatusByEmailUID(ctx context.Context, emailUID int64, status string) error {
	const q = `
        UPDATE process_queue
        SET status = $1
        WHERE email_uid = $2
    `
	_, err := db.Conn.ExecContext(ctx, q, status, emailUID)
	return err
}

// UpdateClassificationByEmailUID — сохранить результат классификации для всех строк письма
func (db *DB) UpdateClassificationByEmailUID(
	ctx context.Context,
	emailUID int64,
	prob1 float64,
	predictedClass *int16,
	modelDecision string,
) error {
	const q = `
        UPDATE process_queue
        SET
            prob_1 = $1,
            predicted_class = $2,
            model_decision = $3
        WHERE email_uid = $4
    `

	var predicted any
	if predictedClass != nil {
		predicted = *predictedClass
	} else {
		predicted = nil
	}

	_, err := db.Conn.ExecContext(ctx, q, prob1, predicted, modelDecision, emailUID)
	return err
}

// HasEmailInQueue проверяет, есть ли уже хотя бы одна строка
// в process_queue для (target_user_id, email_uid).
func (db *DB) HasEmailInQueue(ctx context.Context, targetUserID, emailUID int64) (bool, error) {
    const q = `
        SELECT 1
        FROM process_queue
        WHERE target_user_id = $1 AND email_uid = $2
        LIMIT 1
    `
    var dummy int
    err := db.Conn.QueryRowContext(ctx, q, targetUserID, emailUID).Scan(&dummy)
    if err != nil {
        if err == sql.ErrNoRows {
            return false, nil
        }
        return false, err
    }
    return true, nil
}