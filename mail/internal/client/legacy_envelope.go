package client

import (
	"fmt"

	"github.com/emersion/go-imap/v2"
)

// FetchLegacyEnvelope читает метаданные письма без загрузки тела и без изменения флагов
// found=false - команда успешно завершена, но письмо с указанным UID не возвращено
func (c *Client) FetchLegacyEnvelope(
	uid imap.UID,
) (envelope *imap.Envelope, found bool, err error) {
	if uid == 0 {
		return nil, false, fmt.Errorf(
			"fetch legacy envelope: UID must be non-zero",
		)
	}

	messages, err := c.conn.Fetch(
		imap.UIDSetNum(uid),
		&imap.FetchOptions{
			UID:      true,
			Envelope: true,
		},
	).Collect()
	if err != nil {
		return nil, false, fmt.Errorf(
			"fetch legacy envelope uid=%d: %w",
			uid,
			err,
		)
	}

	var result *imap.Envelope

	for _, message := range messages {
		if message.UID != uid {
			return nil, false, fmt.Errorf(
				"fetch legacy envelope: requested uid=%d, received uid=%d",
				uid,
				message.UID,
			)
		}

		if result != nil {
			return nil, false, fmt.Errorf(
				"fetch legacy envelope: multiple messages for uid=%d",
				uid,
			)
		}

		if message.Envelope == nil {
			return nil, false, fmt.Errorf(
				"fetch legacy envelope: missing envelope for uid=%d",
				uid,
			)
		}

		result = message.Envelope
	}

	c.TouchOK()

	if result == nil {
		return nil, false, nil
	}

	return result, true, nil
}
