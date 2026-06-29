package api

import (
    "context"
    "database/sql"
    "encoding/json"
    "time"
)

type EmailRecord struct {
    ID               int64     `json:"id"`
    UserID           int64     `json:"user_id"`
    Mailbox          string    `json:"mailbox,omitempty"`
    EmailUID         int64     `json:"emailuid"`
    EmailFrom        string    `json:"emailfrom,omitempty"`
    ReplyTo          string    `json:"replyto,omitempty"`
    MessageID        string    `json:"messageid,omitempty"`
    InReplyTo        string    `json:"inreplyto,omitempty"`
    ReferencesHeader string    `json:"references_header,omitempty"`
    EmailSubject     string    `json:"emailsubject,omitempty"`
    RawEmail         string    `json:"rawemail,omitempty"`
    EmailDate        time.Time `json:"emaildate,omitempty"`
    CreatedAt        time.Time `json:"createdat"`
    ToHeader           string
    CcHeader           string
    DeliveredTo        string
    XOriginalTo        string
    EnvelopeTo         string
    XEnvelopeTo        string
    RecipientEmail     string
    RecipientSource    string
    IsPrimaryRecipient bool
}

type DocumentRecord struct {
    ID             int64     `json:"id"`
    EmailID        int64     `json:"email_id"`
    Filename       string    `json:"filename"`
    MinioObjectKey string    `json:"minio_object_key"`
    ContentType    string    `json:"content_type"`
    SizeBytes      int64     `json:"size_bytes"`
    CreatedAt      time.Time `json:"created_at"`
}

type TaskRecord struct {
    ID             int64           `json:"id"`
    EmailID        int64           `json:"email_id"`
    DocumentID     *int64          `json:"document_id,omitempty"`
    Status         string          `json:"status"`
    OutputData     json.RawMessage `json:"output_data,omitempty"`
    ManualDecision json.RawMessage `json:"manual_decision,omitempty"`
    AssignedTo     *int64          `json:"assigned_to,omitempty"`
    ErrorMessage   *string         `json:"error_message,omitempty"`
    RetryCount     int             `json:"retry_count"`
    CreatedAt      time.Time       `json:"created_at"`
    CompletedAt    *time.Time      `json:"completed_at,omitempty"`
}

type QueueEmailItem struct {
    TaskID       int64           `json:"task_id"`
    TaskStatus   string          `json:"task_status"`
    AssignedTo   *int64          `json:"assigned_to,omitempty"`
    OutputData   json.RawMessage `json:"output_data,omitempty"`
    ErrorMessage *string         `json:"error_message,omitempty"`

    EmailID      int64     `json:"emailid"`
    Mailbox      string    `json:"mailbox,omitempty"`
    EmailUID     int64     `json:"emailuid"`
    EmailFrom    string    `json:"emailfrom,omitempty"`
    EmailSubject string    `json:"emailsubject,omitempty"`
    RawEmail     string    `json:"rawemail,omitempty"`
    EmailDate    time.Time `json:"emaildate,omitempty"`

    DocumentNames []string   `json:"document_names"`
    CreatedAt     time.Time  `json:"created_at"`
    CompletedAt   *time.Time `json:"completed_at,omitempty"`
}

type EmailForReply struct {
    ID               int64
    UserID           sql.NullInt64
    Mailbox          string
    EmailUID         int64
    EmailFrom        string
    ReplyTo          string
    MessageID        string
    InReplyTo        string
    ReferencesHeader string
    EmailSubject     string
    RawEmail         string
    EmailDate        sql.NullTime
    ToHeader             string
    CcHeader             string
    DeliveredTo          string
    XOriginalTo          string
    EnvelopeTo           string
    XEnvelopeTo          string
    RecipientEmail       string
    RecipientSource      string
    IsPrimaryRecipient   bool
}

type SentEmailRecord struct {
    ID               int64      `db:"id"`
    UserID           *int64     `db:"user_id"`
    Mailbox          string     `db:"mailbox"`
    EmailUID         *int64     `db:"email_uid"`
    MessageID        string     `db:"message_id"`
    InReplyTo        string     `db:"in_reply_to"`
    ReferencesHeader string     `db:"references_header"`
    ParentEmailID    *int64     `db:"parent_email_id"`
    EmailFrom        string     `db:"email_from"`
    ReplyTo          string     `db:"reply_to"`
    ToHeader         string     `db:"to_header"`
    CcHeader         string     `db:"cc_header"`
    BccHeader        string     `db:"bcc_header"`
    EmailSubject     string     `db:"email_subject"`
    RawEmail         string     `db:"raw_email"`
    EmailDate        *time.Time `db:"email_date"`
    SendStatus       string     `db:"send_status"`
    CreatedAt        time.Time  `db:"created_at"`
    SentAt           time.Time  `db:"sent_at"`
}

type SentDocumentRecord struct {
    ID           int64     `db:"id"`
    SentEmailID  int64     `db:"sent_email_id"`
    Filename     string    `db:"filename"`
    MinioObjectKey string  `db:"minio_object_key"`
    ContentType  string    `db:"content_type"`
    SizeBytes    int64     `db:"size_bytes"`
    CreatedAt    time.Time `db:"created_at"`
}


func (db DB) UpsertEmail(ctx context.Context, rec EmailRecord) (int64, error) {
    const q = `
        INSERT INTO emails (
            user_id,
            mailbox,
            email_uid,
            email_from,
            reply_to,
            message_id,
            in_reply_to,
            references_header,
            email_subject,
            raw_email,
            email_date,
            to_header,
            cc_header,
            delivered_to,
            x_original_to,
            envelope_to,
            x_envelope_to,
            recipient_email,
            recipient_source,
            is_primary_recipient
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
        ON CONFLICT (mailbox, email_uid) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            email_from = EXCLUDED.email_from,
            reply_to = EXCLUDED.reply_to,
            message_id = EXCLUDED.message_id,
            in_reply_to = EXCLUDED.in_reply_to,
            references_header = EXCLUDED.references_header,
            email_subject = EXCLUDED.email_subject,
            raw_email = EXCLUDED.raw_email,
            email_date = EXCLUDED.email_date,
            to_header = EXCLUDED.to_header,
            cc_header = EXCLUDED.cc_header,
            delivered_to = EXCLUDED.delivered_to,
            x_original_to = EXCLUDED.x_original_to,
            envelope_to = EXCLUDED.envelope_to,
            x_envelope_to = EXCLUDED.x_envelope_to,
            recipient_email = EXCLUDED.recipient_email,
            recipient_source = EXCLUDED.recipient_source,
            is_primary_recipient = EXCLUDED.is_primary_recipient
        RETURNING id
    `

    var id int64
    err := db.Conn.QueryRowContext(
        ctx,
        q,
        rec.UserID,
        rec.Mailbox,
        rec.EmailUID,
        rec.EmailFrom,
        rec.ReplyTo,
        rec.MessageID,
        rec.InReplyTo,
        rec.ReferencesHeader,
        rec.EmailSubject,
        rec.RawEmail,
        rec.EmailDate,
        rec.ToHeader,
        rec.CcHeader,
        rec.DeliveredTo,
        rec.XOriginalTo,
        rec.EnvelopeTo,
        rec.XEnvelopeTo,
        rec.RecipientEmail,
        rec.RecipientSource,
        rec.IsPrimaryRecipient,
    ).Scan(&id)
    if err != nil {
        return 0, err
    }

    return id, nil
}

func (db DB) UpsertEmailTx(ctx context.Context, tx *sql.Tx, rec EmailRecord) (int64, error) {
    const q = `
        INSERT INTO emails (
            user_id,
            mailbox,
            email_uid,
            email_from,
            reply_to,
            message_id,
            in_reply_to,
            references_header,
            email_subject,
            raw_email,
            email_date,
            to_header,
            cc_header,
            delivered_to,
            x_original_to,
            envelope_to,
            x_envelope_to,
            recipient_email,
            recipient_source,
            is_primary_recipient
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)
        ON CONFLICT (mailbox, email_uid) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            email_from = EXCLUDED.email_from,
            reply_to = EXCLUDED.reply_to,
            message_id = EXCLUDED.message_id,
            in_reply_to = EXCLUDED.in_reply_to,
            references_header = EXCLUDED.references_header,
            email_subject = EXCLUDED.email_subject,
            raw_email = EXCLUDED.raw_email,
            email_date = EXCLUDED.email_date,
            to_header = EXCLUDED.to_header,
            cc_header = EXCLUDED.cc_header,
            delivered_to = EXCLUDED.delivered_to,
            x_original_to = EXCLUDED.x_original_to,
            envelope_to = EXCLUDED.envelope_to,
            x_envelope_to = EXCLUDED.x_envelope_to,
            recipient_email = EXCLUDED.recipient_email,
            recipient_source = EXCLUDED.recipient_source,
            is_primary_recipient = EXCLUDED.is_primary_recipient
        RETURNING id
    `

    var id int64
    err := tx.QueryRowContext(
        ctx,
        q,
        rec.UserID,
        rec.Mailbox,
        rec.EmailUID,
        rec.EmailFrom,
        rec.ReplyTo,
        rec.MessageID,
        rec.InReplyTo,
        rec.ReferencesHeader,
        rec.EmailSubject,
        rec.RawEmail,
        rec.EmailDate,
        rec.ToHeader,
        rec.CcHeader,
        rec.DeliveredTo,
        rec.XOriginalTo,
        rec.EnvelopeTo,
        rec.XEnvelopeTo,
        rec.RecipientEmail,
        rec.RecipientSource,
        rec.IsPrimaryRecipient,
    ).Scan(&id)
    if err != nil {
        return 0, err
    }

    return id, nil
}

func (db DB) InsertDocument(ctx context.Context, rec DocumentRecord) (int64, error) {
    const q = `
        INSERT INTO documents (
            email_id,
            filename,
            minio_object_key,
            content_type,
            size_bytes
        )
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    `
    var id int64

    err := db.Conn.QueryRowContext(
        ctx,
        q,
        rec.EmailID,
        rec.Filename,
        rec.MinioObjectKey,
        rec.ContentType,
        rec.SizeBytes,
    ).Scan(&id)
    if err != nil {
        return 0, err
    }
    return id, nil
}

func (db DB) InsertDocumentTx(ctx context.Context, tx *sql.Tx, rec DocumentRecord) (int64, error) {
    const q = `
        INSERT INTO documents (
            email_id,
            filename,
            minio_object_key,
            content_type,
            size_bytes
        )
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    `
    var id int64

    err := tx.QueryRowContext(
        ctx,
        q,
        rec.EmailID,
        rec.Filename,
        rec.MinioObjectKey,
        rec.ContentType,
        rec.SizeBytes,
    ).Scan(&id)
    if err != nil {
        return 0, err
    }
    return id, nil
}

func (db DB) CreateTask(ctx context.Context, rec TaskRecord) (int64, error) {
    const q = `
        INSERT INTO tasks (
            email_id,
            document_id,
            status,
            output_data,
            manual_decision,
            assigned_to,
            error_message,
            retry_count,
            completed_at
        )
        VALUES (
            $1,
            $2,
            $3::task_status,
            COALESCE($4::jsonb, '{}'::jsonb),
            $5::jsonb,
            $6,
            $7,
            COALESCE($8, 0),
            $9
        )
        RETURNING id
    `

    var id int64
    err := db.Conn.QueryRowContext(
        ctx,
        q,
        rec.EmailID,
        rec.DocumentID,
        rec.Status,
        jsonOrNil(rec.OutputData),
        jsonOrNil(rec.ManualDecision),
        rec.AssignedTo,
        rec.ErrorMessage,
        rec.RetryCount,
        rec.CompletedAt,
    ).Scan(&id)
    if err != nil {
        return 0, err
    }

    return id, nil
}

func (db DB) CreateTaskTx(ctx context.Context, tx *sql.Tx, rec TaskRecord) (int64, error) {
    const q = `
        INSERT INTO tasks (
            email_id,
            document_id,
            status,
            output_data,
            manual_decision,
            assigned_to,
            error_message,
            retry_count,
            completed_at
        )
        VALUES (
            $1,
            $2,
            $3::task_status,
            COALESCE($4::jsonb, '{}'::jsonb),
            $5::jsonb,
            $6,
            $7,
            COALESCE($8, 0),
            $9
        )
        RETURNING id
    `

    var id int64
    err := tx.QueryRowContext(
        ctx,
        q,
        rec.EmailID,
        rec.DocumentID,
        rec.Status,
        jsonOrNil(rec.OutputData),
        jsonOrNil(rec.ManualDecision),
        rec.AssignedTo,
        rec.ErrorMessage,
        rec.RetryCount,
        rec.CompletedAt,
    ).Scan(&id)
    if err != nil {
        return 0, err
    }

    return id, nil
}

func InsertSentEmailTx(tx *sql.Tx, rec SentEmailRecord) (int64, error) {
    const q = `
        INSERT INTO sent_emails (
            user_id,
            mailbox,
            email_uid,
            message_id,
            in_reply_to,
            references_header,
            parent_email_id,
            email_from,
            reply_to,
            to_header,
            cc_header,
            bcc_header,
            email_subject,
            raw_email,
            email_date,
            send_status,
            created_at,
            sent_at
        )
        VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            $10, $11, $12, $13, $14, $15, $16,
            COALESCE($17, NOW()),
            COALESCE($18, NOW())
        )
        RETURNING id
    `

    var id int64
    err := tx.QueryRowContext(
        context.Background(),
        q,
        rec.UserID,
        rec.Mailbox,
        rec.EmailUID,
        rec.MessageID,
        rec.InReplyTo,
        rec.ReferencesHeader,
        rec.ParentEmailID,
        rec.EmailFrom,
        rec.ReplyTo,
        rec.ToHeader,
        rec.CcHeader,
        rec.BccHeader,
        rec.EmailSubject,
        rec.RawEmail,
        rec.EmailDate,
        rec.SendStatus,
        nullableTime(rec.CreatedAt),
        nullableTime(rec.SentAt),
    ).Scan(&id)
    if err != nil {
        return 0, err
    }

    return id, nil
}

func InsertSentEmail(db *DB, rec SentEmailRecord) (int64, error) {
    tx, err := db.Conn.Begin()
    if err != nil {
        return 0, err
    }
    defer func() {
        _ = tx.Rollback()
    }()

    id, err := InsertSentEmailTx(tx, rec)
    if err != nil {
        return 0, err
    }

    if err := tx.Commit(); err != nil {
        return 0, err
    }

    return id, nil
}

func InsertSentDocumentTx(tx *sql.Tx, rec SentDocumentRecord) (int64, error) {
    const q = `
        INSERT INTO sent_documents (
            sent_email_id,
            filename,
            minio_object_key,
            content_type,
            size_bytes,
            created_at
        )
        VALUES (
            $1, $2, $3, $4, $5,
            COALESCE($6, NOW())
        )
        RETURNING id
    `

    var id int64
    err := tx.QueryRowContext(
        context.Background(),
        q,
        rec.SentEmailID,
        rec.Filename,
        rec.MinioObjectKey,
        rec.ContentType,
        rec.SizeBytes,
        nullableTime(rec.CreatedAt),
    ).Scan(&id)
    if err != nil {
        return 0, err
    }

    return id, nil
}

func InsertSentDocument(db *DB, rec SentDocumentRecord) (int64, error) {
    tx, err := db.Conn.Begin()
    if err != nil {
        return 0, err
    }
    defer func() {
        _ = tx.Rollback()
    }()

    id, err := InsertSentDocumentTx(tx, rec)
    if err != nil {
        return 0, err
    }

    if err := tx.Commit(); err != nil {
        return 0, err
    }

    return id, nil
}

func (db DB) HasEmail(ctx context.Context, mailbox string, emailUID int64) (bool, error) {
    const q = `
        SELECT 1
        FROM emails
        WHERE mailbox = $1 AND email_uid = $2
        LIMIT 1
    `

    var dummy int
    err := db.Conn.QueryRowContext(ctx, q, mailbox, emailUID).Scan(&dummy)
    if err != nil {
        if err == sql.ErrNoRows {
            return false, nil
        }
        return false, err
    }

    return true, nil
}

func (db DB) ListQueueEmails(ctx context.Context, limit int, showCopies bool) ([]QueueEmailItem, error) {
    baseQuery := `
        SELECT
            t.id,
            t.status,
            t.assigned_to,
            COALESCE(t.output_data, '{}'::jsonb) AS output_data,
            t.error_message,
            e.id,
            e.mailbox,
            e.email_uid,
            e.email_from,
            e.email_subject,
            e.raw_email,
            e.email_date,
            COALESCE(
                ARRAY_REMOVE(ARRAY_AGG(DISTINCT d.filename), NULL),
                ARRAY[]::varchar[]
            ) AS document_names,
            t.created_at,
            t.completed_at
        FROM tasks t
        JOIN emails e ON e.id = t.email_id
        LEFT JOIN documents d ON d.email_id = e.id
        WHERE 1=1
    `

    q := baseQuery
    if !showCopies {
        q += " AND e.is_primary_recipient = true"
    }
    
    q += `
        GROUP BY
            t.id, t.status, t.assigned_to, t.output_data, t.error_message,
            e.id, e.mailbox, e.email_uid, e.email_from, e.email_subject, e.raw_email, e.email_date,
            t.created_at, t.completed_at
        ORDER BY t.created_at DESC
        LIMIT $1
    `

    rows, err := db.Conn.QueryContext(ctx, q, limit)
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    var items []QueueEmailItem

    for rows.Next() {
        var it QueueEmailItem
        var outputData []byte
        var assignedTo sql.NullInt64
        var errorMessage sql.NullString
        var mailbox sql.NullString
        var emailFrom sql.NullString
        var emailSubject sql.NullString
        var rawEmail sql.NullString
        var emailDate sql.NullTime
        var completedAt sql.NullTime
        var docNames []string

        err := rows.Scan(
            &it.TaskID,
            &it.TaskStatus,
            &assignedTo,
            &outputData,
            &errorMessage,
            &it.EmailID,
            &mailbox,
            &it.EmailUID,
            &emailFrom,
            &emailSubject,
            &rawEmail,
            &emailDate,
            &docNames,
            &it.CreatedAt,
            &completedAt,
        )
        if err != nil {
            return nil, err
        }

        if assignedTo.Valid {
            v := assignedTo.Int64
            it.AssignedTo = &v
        }
        if len(outputData) > 0 {
            it.OutputData = outputData
        }
        if errorMessage.Valid {
            v := errorMessage.String
            it.ErrorMessage = &v
        }
        if mailbox.Valid {
            it.Mailbox = mailbox.String
        }
        if emailFrom.Valid {
            it.EmailFrom = emailFrom.String
        }
        if emailSubject.Valid {
            it.EmailSubject = emailSubject.String
        }
        if rawEmail.Valid {
            it.RawEmail = rawEmail.String
        }
        if emailDate.Valid {
            it.EmailDate = emailDate.Time
        }
        if completedAt.Valid {
            v := completedAt.Time
            it.CompletedAt = &v
        }

        it.DocumentNames = docNames
        items = append(items, it)
    }

    return items, rows.Err()
}

func (db DB) ListQueueEmailsByStatuses(ctx context.Context, statuses []string, limit int, showCopies bool) ([]QueueEmailItem, error) {
    baseQuery := `
        SELECT
            t.id,
            t.status,
            t.assigned_to,
            COALESCE(t.output_data, '{}'::jsonb) AS output_data,
            t.error_message,
            e.id,
            e.mailbox,
            e.email_uid,
            e.email_from,
            e.email_subject,
            e.raw_email,
            e.email_date,
            COALESCE(
                ARRAY_REMOVE(ARRAY_AGG(DISTINCT d.filename), NULL),
                ARRAY[]::varchar[]
            ) AS document_names,
            t.created_at,
            t.completed_at
        FROM tasks t
        JOIN emails e ON e.id = t.email_id
        LEFT JOIN documents d ON d.email_id = e.id
        WHERE t.status = ANY($1::task_status[])
    `

    q := baseQuery
    if !showCopies {
        q += " AND e.is_primary_recipient = true"
    }
    
    q += `
        GROUP BY
            t.id, t.status, t.assigned_to, t.output_data, t.error_message,
            e.id, e.mailbox, e.email_uid, e.email_from, e.email_subject, e.raw_email, e.email_date,
            t.created_at, t.completed_at
        ORDER BY t.created_at DESC
        LIMIT $2
    `

    rows, err := db.Conn.QueryContext(ctx, q, pqStringArray(statuses), limit)
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    var items []QueueEmailItem

    for rows.Next() {
        var it QueueEmailItem
        var outputData []byte
        var assignedTo sql.NullInt64
        var errorMessage sql.NullString
        var mailbox sql.NullString
        var emailFrom sql.NullString
        var emailSubject sql.NullString
        var rawEmail sql.NullString
        var emailDate sql.NullTime
        var completedAt sql.NullTime
        var docNames []string

        err := rows.Scan(
            &it.TaskID,
            &it.TaskStatus,
            &assignedTo,
            &outputData,
            &errorMessage,
            &it.EmailID,
            &mailbox,
            &it.EmailUID,
            &emailFrom,
            &emailSubject,
            &rawEmail,
            &emailDate,
            &docNames,
            &it.CreatedAt,
            &completedAt,
        )
        if err != nil {
            return nil, err
        }

        if assignedTo.Valid {
            v := assignedTo.Int64
            it.AssignedTo = &v
        }
        if len(outputData) > 0 {
            it.OutputData = outputData
        }
        if errorMessage.Valid {
            v := errorMessage.String
            it.ErrorMessage = &v
        }
        if mailbox.Valid {
            it.Mailbox = mailbox.String
        }
        if emailFrom.Valid {
            it.EmailFrom = emailFrom.String
        }
        if emailSubject.Valid {
            it.EmailSubject = emailSubject.String
        }
        if rawEmail.Valid {
            it.RawEmail = rawEmail.String
        }
        if emailDate.Valid {
            it.EmailDate = emailDate.Time
        }
        if completedAt.Valid {
            v := completedAt.Time
            it.CompletedAt = &v
        }

        it.DocumentNames = docNames
        items = append(items, it)
    }

    return items, rows.Err()
}

func (db DB) GetQueueEmailByTaskID(ctx context.Context, taskID int64) (*QueueEmailItem, error) {
    const q = `
        SELECT
            t.id,
            t.status,
            t.assigned_to,
            COALESCE(t.output_data, '{}'::jsonb) AS output_data,
            t.error_message,
            e.id,
            e.mailbox,
            e.email_uid,
            e.email_from,
            e.email_subject,
            e.raw_email,
            e.email_date,
            COALESCE(
                ARRAY_REMOVE(ARRAY_AGG(DISTINCT d.filename), NULL),
                ARRAY[]::varchar[]
            ) AS document_names,
            t.created_at,
            t.completed_at
        FROM tasks t
        JOIN emails e ON e.id = t.email_id
        LEFT JOIN documents d ON d.email_id = e.id
        WHERE t.id = $1
        GROUP BY
            t.id, t.status, t.assigned_to, t.output_data, t.error_message,
            e.id, e.mailbox, e.email_uid, e.email_from, e.email_subject, e.raw_email, e.email_date,
            t.created_at, t.completed_at
    `

    var it QueueEmailItem
    var outputData []byte
    var assignedTo sql.NullInt64
    var errorMessage sql.NullString
    var mailbox sql.NullString
    var emailFrom sql.NullString
    var emailSubject sql.NullString
    var rawEmail sql.NullString
    var emailDate sql.NullTime
    var completedAt sql.NullTime
    var docNames []string

    err := db.Conn.QueryRowContext(ctx, q, taskID).Scan(
        &it.TaskID,
        &it.TaskStatus,
        &assignedTo,
        &outputData,
        &errorMessage,
        &it.EmailID,
        &mailbox,
        &it.EmailUID,
        &emailFrom,
        &emailSubject,
        &rawEmail,
        &emailDate,
        &docNames,
        &it.CreatedAt,
        &completedAt,
    )
    if err != nil {
        return nil, err
    }

    if assignedTo.Valid {
        v := assignedTo.Int64
        it.AssignedTo = &v
    }
    if len(outputData) > 0 {
        it.OutputData = outputData
    }
    if errorMessage.Valid {
        v := errorMessage.String
        it.ErrorMessage = &v
    }
    if mailbox.Valid {
        it.Mailbox = mailbox.String
    }
    if emailFrom.Valid {
        it.EmailFrom = emailFrom.String
    }
    if emailSubject.Valid {
        it.EmailSubject = emailSubject.String
    }
    if rawEmail.Valid {
        it.RawEmail = rawEmail.String
    }
    if emailDate.Valid {
        it.EmailDate = emailDate.Time
    }
    if completedAt.Valid {
        v := completedAt.Time
        it.CompletedAt = &v
    }

    it.DocumentNames = docNames
    return &it, nil
}

func (db DB) GetEmailForReply(ctx context.Context, id int64) (*EmailForReply, error) {
    const q = `
        SELECT
            id,
            user_id,
            mailbox,
            email_uid,
            COALESCE(email_from, ''),
            COALESCE(reply_to, ''),
            COALESCE(message_id, ''),
            COALESCE(in_reply_to, ''),
            COALESCE(references_header, ''),
            COALESCE(email_subject, ''),
            COALESCE(raw_email, ''),
            email_date,
            COALESCE(to_header, ''),
            COALESCE(cc_header, ''),
            COALESCE(delivered_to, ''),
            COALESCE(x_original_to, ''),
            COALESCE(envelope_to, ''),
            COALESCE(x_envelope_to, ''),
            COALESCE(recipient_email, ''),
            COALESCE(recipient_source, ''),
            COALESCE(is_primary_recipient, false)
        FROM emails
        WHERE id = $1
    `

    var rec EmailForReply
    err := db.Conn.QueryRowContext(ctx, q, id).Scan(
        &rec.ID,
        &rec.UserID,
        &rec.Mailbox,
        &rec.EmailUID,
        &rec.EmailFrom,
        &rec.ReplyTo,
        &rec.MessageID,
        &rec.InReplyTo,
        &rec.ReferencesHeader,
        &rec.EmailSubject,
        &rec.RawEmail,
        &rec.EmailDate,
        &rec.ToHeader,
        &rec.CcHeader,
        &rec.DeliveredTo,
        &rec.XOriginalTo,
        &rec.EnvelopeTo,
        &rec.XEnvelopeTo,
        &rec.RecipientEmail,
        &rec.RecipientSource,
        &rec.IsPrimaryRecipient,
    )
    if err != nil {
        return nil, err
    }

    return &rec, nil
}

func (db DB) ListDocumentsByEmailID(ctx context.Context, emailID int64) ([]DocumentRecord, error) {
	const q = `
		SELECT
			id,
			email_id,
			COALESCE(filename, ''),
			COALESCE(minio_object_key, ''),
			COALESCE(content_type, ''),
			COALESCE(size_bytes, 0),
			created_at
		FROM documents
		WHERE email_id = $1
		ORDER BY id
	`

	rows, err := db.Conn.QueryContext(ctx, q, emailID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var items []DocumentRecord
	for rows.Next() {
		var rec DocumentRecord
		if err := rows.Scan(
			&rec.ID,
			&rec.EmailID,
			&rec.Filename,
			&rec.MinioObjectKey,
			&rec.ContentType,
			&rec.SizeBytes,
			&rec.CreatedAt,
		); err != nil {
			return nil, err
		}
		items = append(items, rec)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return items, nil
}

func (db DB) ListDocumentsByIDsForEmail(ctx context.Context, emailID int64, ids []int64) ([]DocumentRecord, error) {
	if len(ids) == 0 {
		return []DocumentRecord{}, nil
	}

	const q = `
		SELECT
			id,
			email_id,
			COALESCE(filename, ''),
			COALESCE(minio_object_key, ''),
			COALESCE(content_type, ''),
			COALESCE(size_bytes, 0),
			created_at
		FROM documents
		WHERE email_id = $1
		  AND id = ANY($2)
		ORDER BY id
	`

	rows, err := db.Conn.QueryContext(ctx, q, emailID, ids)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var items []DocumentRecord
	for rows.Next() {
		var rec DocumentRecord
		if err := rows.Scan(
			&rec.ID,
			&rec.EmailID,
			&rec.Filename,
			&rec.MinioObjectKey,
			&rec.ContentType,
			&rec.SizeBytes,
			&rec.CreatedAt,
		); err != nil {
			return nil, err
		}
		items = append(items, rec)
	}

	if err := rows.Err(); err != nil {
		return nil, err
	}

	return items, nil
}

func (db DB) UpdateTaskStatus(ctx context.Context, taskID int64, status string, errorMessage *string) error {
    const q = `
        UPDATE tasks
        SET
            status = $1::task_status,
            error_message = $2,
            completed_at = CASE
                WHEN $1 IN ('completed', 'failed', 'skipped') THEN NOW()
                ELSE completed_at
            END
        WHERE id = $3
    `
    _, err := db.Conn.ExecContext(ctx, q, status, errorMessage, taskID)
    return err
}

func (db DB) UpdateTaskOutput(ctx context.Context, taskID int64, outputData json.RawMessage, newStatus *string) error {
    if newStatus != nil {
        const q = `
            UPDATE tasks
            SET
                output_data = COALESCE($1::jsonb, '{}'::jsonb),
                status = $2::task_status,
                completed_at = CASE
                    WHEN $2 IN ('completed', 'failed', 'skipped') THEN NOW()
                    ELSE completed_at
                END
            WHERE id = $3
        `
        _, err := db.Conn.ExecContext(ctx, q, jsonOrNil(outputData), *newStatus, taskID)
        return err
    }

    const q = `
        UPDATE tasks
        SET
            output_data = COALESCE($1::jsonb, '{}'::jsonb)
        WHERE id = $2
    `
    _, err := db.Conn.ExecContext(ctx, q, jsonOrNil(outputData), taskID)
    return err
}

func (db DB) UpdateTaskInput(ctx context.Context, taskID int64, inputData json.RawMessage, newStatus *string) error {
    if newStatus != nil {
        const q = `
            UPDATE tasks
            SET
                input_data = COALESCE($1::jsonb, '{}'::jsonb),
                status = $2::task_status
            WHERE id = $3
        `
        _, err := db.Conn.ExecContext(ctx, q, jsonOrNil(inputData), *newStatus, taskID)
        return err
    }

    const q = `
        UPDATE tasks
        SET
            input_data = COALESCE($1::jsonb, '{}'::jsonb)
        WHERE id = $2
    `
    _, err := db.Conn.ExecContext(ctx, q, jsonOrNil(inputData), taskID)
    return err
}

func (db DB) StartTask(ctx context.Context, taskID int64) error {
    const q = `
        UPDATE tasks
        SET
            status = 'in_progress'::task_status,
            started_at = COALESCE(started_at, NOW())
        WHERE id = $1
    `
    _, err := db.Conn.ExecContext(ctx, q, taskID)
    return err
}

func (db DB) AssignTask(ctx context.Context, taskID int64, assignedTo *int64) error {
    const q = `
        UPDATE tasks
        SET
            assigned_to = $1
        WHERE id = $2
    `
    _, err := db.Conn.ExecContext(ctx, q, assignedTo, taskID)
    return err
}

func byteaOrNil(b []byte) any {
    if len(b) == 0 {
        return nil
    }
    return b
}

func jsonOrNil(v json.RawMessage) any {
    if len(v) == 0 {
        return nil
    }
    return []byte(v)
}

func pqStringArray(items []string) any {
    if items == nil {
        return []string{}
    }
    return items
}

func nullableTime(t time.Time) any {
    if t.IsZero() {
        return nil
    }
    return t
}