package orders

import (
	"log"

	"mail/internal/parser"
	"mail/internal/storage"
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

func (p Processor) ProcessEmail(email parser.Email) error {
	log.Printf("email uid=%d from=%q subject=%q attachments=%d",
		email.UID, email.From, email.Subject, len(email.Files))

	if err := p.repo.SaveOrder(p.userID, email); err != nil {
		return err
	}

	return nil
}
