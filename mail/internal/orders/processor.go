package orders

import (
	//"context"
	"log"

	"OrdersAgent/mail/internal/parser"
	"OrdersAgent/mail/internal/storage"
)


type Processor struct {
	repo               storage.Repository
	userID             int64
}

func New(repo storage.Repository, userID int64) *Processor {
	return &Processor{
		repo:               repo,
		userID:             userID,
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

	return nil
}