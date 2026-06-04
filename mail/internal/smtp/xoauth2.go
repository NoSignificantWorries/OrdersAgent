package smtp

import (
    "fmt"
    "net/smtp"
)

type xoauth2Auth struct {
    username string
    token    string
}

func AuthXOAuth2(username, accessToken string) smtp.Auth {
    return &xoauth2Auth{
        username: username,
        token:    accessToken,
    }
}

func (a *xoauth2Auth) Start(server *smtp.ServerInfo) (string, []byte, error) {
    if server == nil {
        return "", nil, fmt.Errorf("smtp: missing server info")
    }

    // XOAUTH2 payload for SMTP:
    // user=<email>\x01auth=Bearer <token>\x01\x01
    resp := fmt.Sprintf("user=%s\x01auth=Bearer %s\x01\x01", a.username, a.token)

    // Для net/smtp initial response нужно отдавать сырые байты payload.
    return "XOAUTH2", []byte(resp), nil
}

func (a *xoauth2Auth) Next(fromServer []byte, more bool) ([]byte, error) {
    if more {
        // Если сервер всё ещё что-то просит, можно вернуть пустой ответ.
        // Обычно при успешном initial response сюда уже не зайдём.
        return []byte{}, nil
    }
    return nil, nil
}