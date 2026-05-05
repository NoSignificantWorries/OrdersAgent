package orders

import (
	"context"
	"log"

	"OrdersAgent/mail/internal/parser"
	"OrdersAgent/mail/internal/storage"
	temporalclient "OrdersAgent/temporal/client"
)

type Processor struct {
	repo   storage.Repository
	userID int64
}

func New(repo storage.Repository, userID int64) *Processor {
	return &Processor{
		repo:   repo,
		userID: userID,
	}
}

func (p *Processor) ProcessEmail(email *parser.Email) error {
	log.Printf("email uid=%d from=%q subject=%q attachments=%d",
		email.UID, email.From, email.Subject, len(email.Files))

	// Сначала сохраняем письмо и все вложения в process_queue / MinIO
	if err := p.repo.SaveOrder(p.userID, email); err != nil {
		return err
	}

	// После успешного сохранения стартуем один workflow на всё письмо
	workflowID, runID, err := temporalclient.StartProcessEmailWorkflow(context.Background(), int64(email.UID), p.userID)
	if err != nil {
		return err
	}

	log.Printf("email workflow started: email_uid=%d workflowID=%s runID=%s",
		email.UID, workflowID, runID)

	return nil
}