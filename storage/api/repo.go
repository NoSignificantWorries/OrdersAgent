package api

import (
    "context"
    "database/sql"
)

type QueueItem struct {
    ID         int64   `json:"id"`
    AssignedTo *int64  `json:"assigned_to,omitempty"`
    Subject    string  `json:"email_subject"`
    Body       string  `json:"email_body"`
    DocName    *string `json:"document_name,omitempty"`
    DocData    []byte  `json:"-"`
    Status     string  `json:"status"`
    CreatedAt  string  `json:"created_at"`
}

// Вставка записи в очередь
func (db *DB) InsertQueueItem(ctx context.Context, item QueueItem) error {
    const q = `
        INSERT INTO process_queue (
            assigned_to,
            email_subject,
            email_body,
            document_name,
            document_data,
            status
        ) VALUES ($1,$2,$3,$4,$5,$6)
    `

    var assignedTo any
    if item.AssignedTo != nil {
        assignedTo = *item.AssignedTo
    } else {
        assignedTo = nil
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
        item.Subject,
        item.Body,
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
               document_name, status, created_at
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

        if err := rows.Scan(
            &it.ID,
            &assignedTo,
            &it.Subject,
            &it.Body,
            &docName,
            &it.Status,
            &it.CreatedAt,
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

        res = append(res, it)
    }

    return res, rows.Err()
}
