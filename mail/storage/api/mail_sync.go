package api

import (
	"context"
	"fmt"
)

const maxIMAPUID int64 = 4294967295

type MailSyncState struct {
	UserID            int64
	UIDValidity       uint32
	LastReconciledUID int64
}

// GetOrCreateMailSyncState создаёт исходную границу только при отсутствии состояния
func (db DB) GetOrCreateMailSyncState(
	ctx context.Context,
	userID int64,
	uidValidity uint32,
	initialUID int64,
) (MailSyncState, bool, error) {
	var state MailSyncState

	if userID <= 0 {
		return state, false, fmt.Errorf("invalid user_id=%d", userID)
	}
	if uidValidity == 0 {
		return state, false, fmt.Errorf("invalid UIDVALIDITY=0")
	}
	if initialUID < 0 || initialUID > maxIMAPUID {
		return state, false, fmt.Errorf(
			"invalid initial UID=%d",
			initialUID,
		)
	}

	tx, err := db.Conn.BeginTx(ctx, nil)
	if err != nil {
		return state, false, fmt.Errorf("begin mail sync state tx: %w", err)
	}
	defer func() {
		_ = tx.Rollback()
	}()

	result, err := tx.ExecContext(
		ctx,
		`
            INSERT INTO mail_sync_state (
                user_id,
                uid_validity,
                last_reconciled_uid
            )
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO NOTHING
        `,
		userID,
		uidValidity,
		initialUID,
	)
	if err != nil {
		return state, false, fmt.Errorf("insert mail sync state: %w", err)
	}

	inserted, err := result.RowsAffected()
	if err != nil {
		return state, false, fmt.Errorf(
			"read mail sync insert result: %w",
			err,
		)
	}

	var storedValidity int64

	err = tx.QueryRowContext(
		ctx,
		`
            SELECT user_id, uid_validity, last_reconciled_uid
            FROM mail_sync_state
            WHERE user_id = $1
            FOR UPDATE
        `,
		userID,
	).Scan(
		&state.UserID,
		&storedValidity,
		&state.LastReconciledUID,
	)
	if err != nil {
		return state, false, fmt.Errorf("read mail sync state: %w", err)
	}

	if storedValidity != int64(uidValidity) {
		return state, false, fmt.Errorf(
			"UIDVALIDITY changed: user_id=%d stored=%d server=%d; import must be stopped",
			userID,
			storedValidity,
			uidValidity,
		)
	}

	state.UIDValidity = uidValidity

	if err := tx.Commit(); err != nil {
		return MailSyncState{}, false, fmt.Errorf(
			"commit mail sync state tx: %w",
			err,
		)
	}

	return state, inserted == 1, nil
}

// AdvanceMailSyncState продвигает границу только из ожидаемого состояния
func (db DB) AdvanceMailSyncState(
	ctx context.Context,
	userID int64,
	uidValidity uint32,
	expectedUID int64,
	nextUID int64,
) error {
	if userID <= 0 {
		return fmt.Errorf("invalid user_id=%d", userID)
	}
	if uidValidity == 0 {
		return fmt.Errorf("invalid UIDVALIDITY=0")
	}
	if expectedUID < 0 || expectedUID > maxIMAPUID {
		return fmt.Errorf("invalid expected UID=%d", expectedUID)
	}
	if nextUID < expectedUID || nextUID > maxIMAPUID {
		return fmt.Errorf(
			"invalid checkpoint advance: from=%d to=%d",
			expectedUID,
			nextUID,
		)
	}

	result, err := db.Conn.ExecContext(
		ctx,
		`
            UPDATE mail_sync_state
            SET
                last_reconciled_uid = $4,
                updated_at = NOW()
            WHERE user_id = $1
              AND uid_validity = $2
              AND last_reconciled_uid = $3
        `,
		userID,
		uidValidity,
		expectedUID,
		nextUID,
	)
	if err != nil {
		return fmt.Errorf("advance mail sync state: %w", err)
	}

	updated, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("read mail sync update result: %w", err)
	}

	if updated != 1 {
		return fmt.Errorf(
			"mail sync state not advanced: user_id=%d uid_validity=%d expected_uid=%d; state is missing or changed",
			userID,
			uidValidity,
			expectedUID,
		)
	}

	return nil
}
