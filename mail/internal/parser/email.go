package parser

import (
	"encoding/base64"
	"bytes"
	"fmt"
	"io"
	"log"
	"mime"
	"strconv"
	"strings"
	"bufio"
    "net/mail"

	htmllib "golang.org/x/net/html"

	"github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
	_ "github.com/emersion/go-message/charset"
	msgmail "github.com/emersion/go-message/mail"
	"golang.org/x/text/encoding/charmap"
)

type Email struct {
	UID     imap.UID
	From    string
	Subject string
	Date    string
	Body    string
	Files   []Attachment
	MessageID        string
	InReplyTo        string
	ReferencesHeader string
	ReplyTo          string
}

type Attachment struct {
	Name string
	Data []byte
}

func decodeBodyBytes(b []byte, contentType string) string {
    if len(b) == 0 {
        return ""
    }

    // Пытаемся вытащить charset из Content-Type
    _, params, err := mime.ParseMediaType(contentType)
    charsetName := ""
    if err == nil {
        charsetName = strings.ToLower(strings.TrimSpace(params["charset"]))
    }

    // По умолчанию считаем UTF-8
    if charsetName == "" || charsetName == "utf-8" || charsetName == "us-ascii" {
		return string(b)
	}

    switch charsetName {
    case "windows-1251", "cp1251":
        decoded, err := charmap.Windows1251.NewDecoder().Bytes(b)
        if err == nil {
            return string(decoded)
        }
    case "koi8-r":
        decoded, err := charmap.KOI8R.NewDecoder().Bytes(b)
        if err == nil {
            return string(decoded)
        }
    // при необходимости можно добавить другие чарсеты
    }

    // Fallback — возвращаем как есть
    return string(b)
}

func extractNestedMessageText(raw []byte) string {
    r := bytes.NewReader(raw)
    mr, err := msgmail.CreateReader(r)
    if err != nil {
        return strings.TrimSpace(extractTextFromHTML(string(raw)))
    }

    var plainPart, htmlPart string

    for {
        p, err := mr.NextPart()
        if err == io.EOF {
            break
        }
        if err != nil {
            break
        }

        contentType := p.Header.Get("Content-Type")
        ctLower := strings.ToLower(contentType)
        bodyBytes, _ := io.ReadAll(p.Body)

        if strings.HasPrefix(ctLower, "text/plain") {
            txt := strings.TrimSpace(decodeBodyBytes(bodyBytes, contentType))
            if txt != "" && plainPart == "" {
                plainPart = txt
            }
        } else if strings.HasPrefix(ctLower, "text/html") {
            html := decodeBodyBytes(bodyBytes, contentType)
            txt := strings.TrimSpace(extractTextFromHTML(html))
            if txt != "" && htmlPart == "" {
                htmlPart = txt
            }
        }
    }

    if plainPart != "" {
        return plainPart
    }
    if htmlPart != "" {
        return htmlPart
    }
    return ""
}

func joinAddresses(addrs []imap.Address) string {
    parts := make([]string, 0, len(addrs))
    for _, addr := range addrs {
        if addr.Mailbox == "" || addr.Host == "" {
            continue
        }

        email := fmt.Sprintf("%s@%s", addr.Mailbox, addr.Host)
        name := strings.TrimSpace(decodeHeader(addr.Name))

        if name != "" {
            parts = append(parts, fmt.Sprintf("%s <%s>", name, email))
        } else {
            parts = append(parts, email)
        }
    }
    return strings.Join(parts, ", ")
}

func firstAddress(addrs []imap.Address) string {
    for _, addr := range addrs {
        if addr.Mailbox == "" || addr.Host == "" {
            continue
        }
        return fmt.Sprintf("%s@%s", addr.Mailbox, addr.Host)
    }
    return ""
}

func parseHeaderFields(r io.Reader) (messageID, inReplyTo, references, replyTo string, err error) {
    mr, err := mail.ReadMessage(bufio.NewReader(r))
    if err != nil {
        return "", "", "", "", err
    }

    h := mr.Header

    messageID = strings.TrimSpace(h.Get("Message-ID"))
    inReplyTo = strings.TrimSpace(h.Get("In-Reply-To"))
    references = strings.TrimSpace(h.Get("References"))
    replyTo = strings.TrimSpace(h.Get("Reply-To"))

    return messageID, inReplyTo, references, replyTo, nil
}

func decodeHeader(s string) string {
	if s == "" {
		return s
	}

	// 1. Стандартный декодер (работает для UTF-8)
	d := new(mime.WordDecoder)
	if decoded, err := d.DecodeHeader(s); err == nil && decoded != s {
		return decoded
	}

	// 2. Специальные кодировки
	if strings.Contains(s, "koi8-r") {
		return decodeKoi8R(s)
	}
	if strings.Contains(s, "windows-1251") {
		return decodeWindows1251(s)
	}

	return s
}

func decodeWindows1251(s string) string {
	parts := strings.Fields(s)
	var result []string

	for _, p := range parts {
		// B-кодировка
		if strings.HasPrefix(p, "=?windows-1251?B?") && strings.HasSuffix(p, "?=") {
			idxB := strings.Index(p, "?B?")
			if idxB == -1 {
				continue
			}
			data := p[idxB+3 : len(p)-2]
			decodedBytes, err := base64.StdEncoding.DecodeString(data)
			if err != nil {
				continue
			}
			decoded, err := charmap.Windows1251.NewDecoder().String(string(decodedBytes))
			if err == nil {
				result = append(result, decoded)
			}
			continue
		}

		// Q-кодировка
		if strings.HasPrefix(p, "=?windows-1251?Q?") && strings.HasSuffix(p, "?=") {
			idxQ := strings.Index(p, "?Q?")
			if idxQ == -1 {
				continue
			}
			data := p[idxQ+3 : len(p)-2]
			decodedBytes := decodeQuotedPrintable(data)
			decoded, err := charmap.Windows1251.NewDecoder().String(string(decodedBytes))
			if err == nil {
				result = append(result, decoded)
			}
			continue
		}
	}

	if len(result) > 0 {
		return strings.Join(result, " ")
	}
	return s
}

func decodeKoi8R(s string) string {
	parts := strings.Fields(s)
	var result []string

	for _, p := range parts {
		if !strings.HasPrefix(p, "=?koi8-r?B?") || !strings.HasSuffix(p, "?=") {
			continue
		}

		// Извлекаем base64 данные
		idxB := strings.Index(p, "?B?")
		if idxB == -1 {
			continue
		}
		data := p[idxB+3 : len(p)-2]

		decodedBytes, err := base64.StdEncoding.DecodeString(data)
		if err != nil {
			continue
		}

		// KOI8-R в UTF-8
		decoded, err := charmap.KOI8R.NewDecoder().String(string(decodedBytes))
		if err == nil {
			result = append(result, decoded)
		}
	}

	if len(result) > 0 {
		return strings.Join(result, " ")
	}
	return s
}

// Вспомогательная функция для Quoted-Printable
func decodeQuotedPrintable(s string) []byte {
	var result []byte
	i := 0
	for i < len(s) {
		if s[i] == '=' && i+2 < len(s) {
			if s[i+1] == '\r' && s[i+2] == '\n' {
				i += 3
				continue
			}
			hex := s[i+1 : i+3]
			if v, err := strconv.ParseUint("0x"+string(hex), 0, 8); err == nil {
				result = append(result, byte(v))
				i += 3
				continue
			}
		}
		result = append(result, s[i])
		i++
	}
	return result
}

func ParseMessage(uid imap.UID, fetchCmd *imapclient.FetchCommand) (*Email, error) {
    msg := fetchCmd.Next()
    if msg == nil {
        return nil, fmt.Errorf("no message")
    }

    email := &Email{
        UID: uid,
    }

    var bodyError error

    for {
        item := msg.Next()
        if item == nil {
            break
        }

        if env, ok := item.(imapclient.FetchItemDataEnvelope); ok {
            email.Subject = decodeHeader(env.Envelope.Subject)
            email.From = joinAddresses(env.Envelope.From)

            if !env.Envelope.Date.IsZero() {
                email.Date = env.Envelope.Date.Format("2006-01-02 15:04")
            }

            email.MessageID = strings.TrimSpace(env.Envelope.MessageID)
            if len(env.Envelope.InReplyTo) > 0 {
				email.InReplyTo = strings.TrimSpace(env.Envelope.InReplyTo[0])
			}
            email.ReplyTo = firstAddress(env.Envelope.ReplyTo)

            continue
        }

        if bodyData, ok := item.(imapclient.FetchItemDataBodySection); ok && bodyData.Literal != nil {
            section := bodyData.Section

            if section != nil && section.Specifier == imap.PartSpecifierHeader {
                msgID, inReplyTo, refs, replyTo, err := parseHeaderFields(bodyData.Literal)
                if err != nil {
                    log.Printf("parseHeaderFields: UID=%d err=%v", email.UID, err)
                    continue
                }

                if email.MessageID == "" {
                    email.MessageID = msgID
                }
                if email.InReplyTo == "" {
                    email.InReplyTo = inReplyTo
                }
				log.Printf("InReplyTo: %s", email.InReplyTo)
                if email.ReferencesHeader == "" {
                    email.ReferencesHeader = refs
                }
				log.Printf("ReferencesHeader: %s", email.ReferencesHeader)
                if email.ReplyTo == "" {
                    email.ReplyTo = replyTo
                }
				log.Printf("ReplyTo: %s", email.ReplyTo)

                continue
            }

            if err := parseBody(email, bodyData.Literal); err != nil {
                bodyError = err
            }
            continue
        }
    }

    return email, bodyError
}

func cleanBodyText(body string) string {
    // 1. Убираем явный CSS/HTML‑мусор, но не контент
    lines := strings.Split(body, "\n")
    cleaned := make([]string, 0, len(lines))

    prevEmpty := false

    for _, raw := range lines {
        line := strings.TrimRight(raw, " \t\r")

        // Удаляем явный техмусор
        trimmed := strings.TrimSpace(line)
        if trimmed == "" {
            // схлопываем пачки пустых строк в одну
            if !prevEmpty {
                cleaned = append(cleaned, "")
                prevEmpty = true
            }
            continue
        }
        prevEmpty = false

        // CSS/HTML‑мусор
        if strings.Contains(trimmed, "blockquote.rt") ||
            strings.HasPrefix(trimmed, "p {") ||
            strings.Contains(trimmed, ".email-signature") {
            continue
        }

        // Ничего не обрываем по "С уважением" и т.п.
        cleaned = append(cleaned, trimmed)
    }

    res := strings.Join(cleaned, "\n")

    // Убираем ведущие/замыкающие пустые строки
    res = strings.Trim(res, "\n")
    return res
}

func parseBody(email *Email, literal io.Reader) error {
    mr, err := msgmail.CreateReader(literal)
    if err != nil {
        return fmt.Errorf("parsing body: %w", err)
    }

    var plainPart string
    var htmlPart string
    var nestedPart string

    for {
        p, err := mr.NextPart()
        if err == io.EOF {
            break
        }
        if err != nil {
            log.Printf("NextPart error UID=%d: %v", email.UID, err)
            continue
        }

        contentType := p.Header.Get("Content-Type")
        disp := p.Header.Get("Content-Disposition")
        ctLower := strings.ToLower(contentType)

        switch {
        // ---------------- text/plain ----------------
        case strings.HasPrefix(ctLower, "text/plain"):
            bodyBytes, _ := io.ReadAll(p.Body)
            txt := decodeBodyBytes(bodyBytes, contentType)
            txt = strings.TrimSpace(txt)
            if txt != "" {
                // Если уже был plain, второй не добавляем, чтобы не дублировать
                if plainPart == "" {
                    plainPart = txt
                } else {
                    // можно залогировать, что plain дублируется
                    log.Printf("UID=%d: extra text/plain part skipped", email.UID)
                }
            }

        // ---------------- text/html ----------------
        case strings.HasPrefix(ctLower, "text/html"):
            bodyBytes, _ := io.ReadAll(p.Body)
            html := decodeBodyBytes(bodyBytes, contentType)
            txt := strings.TrimSpace(extractTextFromHTML(html))
            if txt != "" && htmlPart == "" {
                htmlPart = txt
            }

        // ---------------- вложенное письмо message/rfc822 ----------------
        case strings.HasPrefix(ctLower, "message/rfc822"):
            nestedBytes, _ := io.ReadAll(p.Body)
            if len(nestedBytes) > 0 && nestedPart == "" {
                nestedText := extractNestedMessageText(nestedBytes)
                if nestedText != "" {
                    nestedPart = nestedText
                }
            }

        // ---------------- вложения ----------------
        default:
            if strings.Contains(strings.ToLower(disp), "attachment") ||
                strings.HasPrefix(ctLower, "application/") ||
                strings.HasPrefix(ctLower, "image/") {

                name := extractFilename(disp, contentType)
                if name == "" {
                    continue
                }
                att := Attachment{Name: name}
                att.Data, _ = io.ReadAll(p.Body)
                email.Files = append(email.Files, att)
            }
        }
    }

    // Выбор лучшей ветки
    var body string
    plain := strings.TrimSpace(plainPart)
	html := strings.TrimSpace(htmlPart)
	nested := strings.TrimSpace(nestedPart)

	switch {
	case plain != "" && len([]rune(plain)) > 30:
		body = plain
	case nested != "":
		body = nested
	case html != "":
		body = html
	case plain != "":
		body = plain
	default:
		body = ""
	}

    email.Body = cleanBodyText(body)
    return nil
}

// чистый текст из HTML
func extractTextFromHTML(htmlStr string) string {
	doc, err := htmllib.Parse(strings.NewReader(htmlStr))
	if err != nil {
		return htmlStr
	}

	var b strings.Builder

	blockTags := map[string]bool{
		"p": true, "div": true, "section": true, "article": true,
		"header": true, "footer": true, "aside": true,
		"table": true, "thead": true, "tbody": true, "tfoot": true,
		"tr": true, "td": true, "th": true,
		"ul": true, "ol": true, "li": true,
		"blockquote": true, "pre": true,
		"h1": true, "h2": true, "h3": true, "h4": true, "h5": true, "h6": true,
	}

	skipTags := map[string]bool{
		"script": true,
		"style":  true,
		"noscript": true,
	}

	var walk func(*htmllib.Node, bool)
	walk = func(n *htmllib.Node, skip bool) {
		if n == nil {
			return
		}

		if n.Type == htmllib.ElementNode {
			if skipTags[n.Data] {
				skip = true
			}

			if n.Data == "br" {
				b.WriteString("\n")
			} else if blockTags[n.Data] {
				b.WriteString("\n")
			}
		}

		if !skip && n.Type == htmllib.TextNode {
			txt := strings.TrimSpace(n.Data)
			if txt != "" {
				b.WriteString(txt)
				b.WriteString(" ")
			}
		}

		for c := n.FirstChild; c != nil; c = c.NextSibling {
			walk(c, skip)
		}

		if n.Type == htmllib.ElementNode && blockTags[n.Data] {
			b.WriteString("\n")
		}
	}

	walk(doc, false)

	rawLines := strings.Split(b.String(), "\n")
	cleaned := make([]string, 0, len(rawLines))
	prevEmpty := false

	for _, line := range rawLines {
		line = strings.Join(strings.Fields(line), " ")
		if line == "" {
			if !prevEmpty {
				cleaned = append(cleaned, "")
				prevEmpty = true
			}
			continue
		}
		cleaned = append(cleaned, line)
		prevEmpty = false
	}

	return strings.TrimSpace(strings.Join(cleaned, "\n"))
}

func extractFilename(disposition, contentType string) string {
	var filename string

	if idx := strings.Index(disposition, "filename="); idx >= 0 {
		rawFilename := disposition[idx+9:]
		rawFilename = strings.Trim(rawFilename, "\"")

		filename = decodeHeader(rawFilename)
	}

	// Если имени нет  это мусорное вложение (подпись и т.п.)
	if filename == "" {
		return ""
	}

	// Очистка опасных символов
	filename = strings.Map(func(r rune) rune {
		switch r {
		case '/', '\\', ':', '*', '?', '"', '<', '>', '|':
			return '_'
		}
		return r
	}, filename)

	return filename
}
