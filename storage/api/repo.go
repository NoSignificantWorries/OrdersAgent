package api

import (
    "context"
    "database/sql"
    "time"
)

type QueueItem struct {
    ID         int64   `json:"id"`
    AssignedTo *int64  `json:"assigned_to,omitempty"`
    TargetUserID int64   `json:"target_user_id"`
    Subject    string  `json:"email_subject"`
    Body       string  `json:"email_body"`
    EmailUID       *int64   `json:"email_uid,omitempty"`
    EmailFrom      *string    `json:"email_from,omitempty"`
    EmailDate      *time.Time `json:"email_date,omitempty"`
    DocName    *string `json:"document_name,omitempty"`
    DocData    []byte  `json:"-"`
    Status     string  `json:"status"`
    CreatedAt  string  `json:"created_at"`
    Prob1         *float64 `json:"prob_1,omitempty"`
    PredictedClass *int16  `json:"predicted_class,omitempty"`
    ModelDecision *string  `json:"model_decision,omitempty"`
}

// Вставка записи в очередь
func (db *DB) InsertQueueItem(ctx context.Context, item QueueItem) error {
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
            document_data,
            status
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
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

    _, err := db.Conn.ExecContext(
        ctx, q,
        assignedTo,
        item.TargetUserID,
        item.Subject,
        item.Body,
        emailUID,
        item.EmailFrom,
        item.EmailDate,
        docName,
        item.DocData,
        item.Status,
    )
    return err
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

        if err := rows.Scan(
            &it.ID,
            &assignedTo,
            &it.Subject,
            &it.Body,
            &docName,
            &it.Status,
            &it.CreatedAt,
            &prob1,
            &predClass,
            &modelDecision,
        ); err != nil {
            return nil, err
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
