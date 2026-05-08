package orders

import (
	"context"
	"log"

	"OrdersAgent/mail/parser"
	"OrdersAgent/mail/storage"
)

type StartEmailWorkflowFunc func(ctx context.Context, emailUID, userID int64) error

type Processor struct {
	repo               storage.Repository
	userID             int64
	startEmailWorkflow StartEmailWorkflowFunc
}

func New(repo storage.Repository, userID int64, startEmailWorkflow StartEmailWorkflowFunc) *Processor {
	return &Processor{
		repo:               repo,
		userID:             userID,
		startEmailWorkflow: startEmailWorkflow,
	}
}

func (p *Processor) ProcessEmail(email *parser.Email) error {
	log.Printf("email uid=%d from=%q subject=%q attachments=%d",
		email.UID, email.From, email.Subject, len(email.Files))

	emailUID := int64(email.UID)

	// Есть ли уже такое письмо в очереди для этого пользователя
	exists, err := p.repo.HasEmailInQueue(p.userID, emailUID)
	if err != nil {
		return err
	}

	if exists {
		log.Printf("email uid=%d already exists in process_queue for user_id=%d, skipping", emailUID, p.userID)
		return nil
	}

	// Сохраняем письмо и все вложения в process_queue / MinIO
	if err := p.repo.SaveOrder(p.userID, email); err != nil {
		return err
	}

	// После успешного сохранения стартуем один workflow на всё письмо,
	// но только если callback был передан извне.
	if p.startEmailWorkflow != nil {
		if err := p.startEmailWorkflow(context.Background(), emailUID, p.userID); err != nil {
			return err
		}

		log.Printf("email workflow started: email_uid=%d user_id=%d", email.UID, p.userID)
	} else {
		log.Printf("email saved without workflow start: email_uid=%d user_id=%d", email.UID, p.userID)
	}

	return nil
}