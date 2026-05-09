package storage

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"time"

	"OrdersAgent/mail/internal/parser"
	"OrdersAgent/storage/api"
	minio "worker/minio/minio"
)

// Repository — общий интерфейс хранилища.
type Repository interface {
	SaveFile(att parser.Attachment) error
	SaveOrder(userID int64, order any) error
	HasEmailInQueue(userID, emailUID int64) (bool, error)
}

// UserMailAuth — OAuth‑данные почты пользователя из таблицы users.
type UserMailAuth struct {
	Email           string
	AccessToken     string
	RefreshToken    string
	AccessExpiresAt time.Time
}

// MailUser — пользователь, у которого настроена почта.
type MailUser struct {
	ID    int64
	Email string
}

// FileRepo — старая файловая реализация (если больше не нужна, можно удалить целиком).
type FileRepo struct{}

func NewFileRepo() Repository {
	return &FileRepo{}
}

func (f *FileRepo) SaveFile(att parser.Attachment) error {
	return fmt.Errorf("FileRepo.SaveFile is deprecated")
}

func (f *FileRepo) SaveOrder(userID int64, order any) error {
	return nil
}

func (f *FileRepo) HasEmailInQueue(userID, emailUID int64) (bool, error) {
	return false, nil
}

// DBRepo — пишет метаданные в Postgres и файлы в MinIO.
type DBRepo struct {
	db    *api.DB
	store *minio.CloudStorage
}

// NewDBRepo — создаёт репозиторий с Postgres и MinIO.
func NewDBRepo(db *api.DB, store *minio.CloudStorage) Repository {
	return &DBRepo{
		db:    db,
		store: store,
	}
}

// GetUserMailAuth достаёт из users email и почтовые OAuth‑токены.
func GetUserMailAuth(db *api.DB, userID int64) (*UserMailAuth, error) {
	row := db.Conn.QueryRow(`
        SELECT
            email,
            mail_access_token,
            mail_refresh_token,
            mail_access_expires_at
        FROM users
        WHERE id = $1
    `, userID)

	var email string
	var accessToken sql.NullString
	var refreshToken sql.NullString
	var accessExpiresAt sql.NullTime

	if err := row.Scan(&email, &accessToken, &refreshToken, &accessExpiresAt); err != nil {
		if err == sql.ErrNoRows {
			return nil, fmt.Errorf("user not found: id=%d", userID)
		}
		return nil, fmt.Errorf("query user mail auth: %w", err)
	}

	if !accessToken.Valid || accessToken.String == "" {
		return nil, fmt.Errorf("user id=%d has no mail_access_token", userID)
	}

	if !accessExpiresAt.Valid {
		return nil, fmt.Errorf("user id=%d has no mail_access_expires_at", userID)
	}

	auth := &UserMailAuth{
		Email:           email,
		AccessToken:     accessToken.String,
		AccessExpiresAt: accessExpiresAt.Time,
	}

	if refreshToken.Valid {
		auth.RefreshToken = refreshToken.String
	}

	return auth, nil
}

// SaveFile сейчас не используется, всё делаем через SaveOrder.
func (r *DBRepo) SaveFile(att parser.Attachment) error {
	return nil
}

// SaveOrder — сохраняет письмо и вложения в MinIO и process_queue.
func (r *DBRepo) SaveOrder(userID int64, order any) error {
	email, ok := order.(*parser.Email)
	if !ok {
		return fmt.Errorf("SaveOrder: expected *parser.Email, got %T", order)
	}

	ctx := context.Background()
	managerID := int64(1)
	emailUID := int64(email.UID)

	var emailFrom *string
	if email.From != "" {
		from := email.From
		emailFrom = &from
	}

	var emailDate *time.Time
	if email.Date != "" {
		if parsed, err := time.Parse("2006-01-02 15:04", email.Date); err == nil {
			emailDate = &parsed
		}
	}

	bucket := os.Getenv("MINIO_BUCKET")
	if bucket == "" {
		bucket = "orders-attachments"
	}

	if len(email.Files) > 0 {
		for i, f := range email.Files {
			name := f.Name

			// object key по схеме {email_uid}/{index}_{filename}
			objectKey := fmt.Sprintf("%d/%d_%s", emailUID, i+1, name)

			// 1. грузим файл в MinIO
			if err := r.store.Upload(ctx, objectKey, f.Data); err != nil {
				return fmt.Errorf("upload attachment %s (key=%s): %w", name, objectKey, err)
			}

			// 2. пишем строку в process_queue
			item := api.QueueItem{
				AssignedTo:   &managerID,
				TargetUserID: userID,
				Subject:      email.Subject,
				Body:         email.Body,
				EmailUID:     &emailUID,
				EmailFrom:    emailFrom,
				EmailDate:    emailDate,
				DocName:      &name,
				ObjectBucket: &bucket,
				ObjectKey:    &objectKey,
				Status:       "wait",
			}

			_, err := r.db.InsertQueueItem(ctx, item)
			if err != nil {
				return fmt.Errorf("insert queue item (uid=%d, key=%s): %w", emailUID, objectKey, err)
			}
		}
		return nil
	}

	// Если вложений нет — одна запись без document_name/object_key
	item := api.QueueItem{
		AssignedTo:   &managerID,
		TargetUserID: userID,
		Subject:      email.Subject,
		Body:         email.Body,
		EmailUID:     &emailUID,
		EmailFrom:    emailFrom,
		EmailDate:    emailDate,
		DocName:      nil,
		ObjectBucket: nil,
		ObjectKey:    nil,
		Status:       "wait",
	}

	_, err := r.db.InsertQueueItem(ctx, item)
	if err != nil {
		return fmt.Errorf("insert queue item (uid=%d, no attachments): %w", emailUID, err)
	}

	return nil
}

func (r *DBRepo) HasEmailInQueue(userID, emailUID int64) (bool, error) {
	ctx := context.Background()
	return r.db.HasEmailInQueue(ctx, userID, emailUID)
}

// UpdateUserMailTokens — обновляет почтовые токены пользователя в таблице users.
func UpdateUserMailTokens(db *api.DB, userID int64, auth *UserMailAuth) error {
	_, err := db.Conn.Exec(`
        UPDATE users
        SET
            mail_access_token = $1,
            mail_refresh_token = $2,
            mail_access_expires_at = $3
        WHERE id = $4
    `,
		auth.AccessToken,
		auth.RefreshToken,
		auth.AccessExpiresAt,
		userID,
	)
	if err != nil {
		return fmt.Errorf("update user mail tokens: %w", err)
	}
	return nil
}

// GetUsersWithMailAuth — возвращает всех пользователей, у которых есть почтовые токены.
func GetUsersWithMailAuth(db *api.DB) ([]MailUser, error) {
	rows, err := db.Conn.Query(`
        SELECT id, email
        FROM users
        WHERE mail_access_token IS NOT NULL
          AND mail_access_expires_at IS NOT NULL
        ORDER BY id
    `)
	if err != nil {
		return nil, fmt.Errorf("query users with mail auth: %w", err)
	}
	defer rows.Close()

	var users []MailUser
	for rows.Next() {
		var u MailUser
		if err := rows.Scan(&u.ID, &u.Email); err != nil {
			return nil, fmt.Errorf("scan user with mail auth: %w", err)
		}
		users = append(users, u)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("rows users with mail auth: %w", err)
	}

	return users, nil
}