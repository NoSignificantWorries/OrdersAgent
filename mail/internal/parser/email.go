package parser

import (
	"bytes"
	"fmt"
	"io"
	"log"
	"mime"
	"strings"
	"bufio"
    "net/mail"
    "regexp"
    "time"

	htmllib "golang.org/x/net/html"

	"github.com/emersion/go-imap/v2"
	"github.com/emersion/go-imap/v2/imapclient"
    "github.com/emersion/go-message"
	_ "github.com/emersion/go-message/charset"
	msgmail "github.com/emersion/go-message/mail"
	"golang.org/x/text/encoding/charmap"
)

type Email struct {
	UID     imap.UID
    Mailbox string
	From    string
	Subject string
	Date    string
	Body    string
	Files   []Attachment
	MessageID        string
	InReplyTo        string
	ReferencesHeader string
	ReplyTo          string
    To                 string
    Cc                 string
    DeliveredTo        string
    XOriginalTo        string
    EnvelopeTo         string
    XEnvelopeTo        string
    RecipientEmail     string
    RecipientSource    string
    IsPrimaryRecipient bool
}

type Attachment struct {
	Name string
	Data []byte
}

func decodeBodyBytes(b []byte, contentType string) string {
    if len(b) == 0 {
        return ""
    }
    return string(b)
}

var imagePlaceholderRe = regexp.MustCompile(`\s*\[image:[^\]]+\]`)

func extractNestedMessage(raw []byte) (text string, attachments []Attachment) {
    if len(raw) == 0 {
        return "", nil
    }

    nestedEmail := &Email{}

    if err := parseBody(nestedEmail, bytes.NewReader(raw)); err != nil {
        log.Printf("nested message parse error: %v", err)

        // Если MIME-разбор невозможен, хотя бы возвращаем текст
        return strings.TrimSpace(extractTextFromHTML(string(raw))), nil
    }

    return nestedEmail.Body, nestedEmail.Files
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

func parseHeaderFields(r io.Reader) (messageID, inReplyTo, references, replyTo string, to, cc, 
    deliveredTo, xOriginalTo, envelopeTo, xEnvelopeTo string, err error) {
    mr, err := mail.ReadMessage(bufio.NewReader(r))
    if err != nil {
        return "", "", "", "", "", "", "", "", "", "", err
    }

    h := mr.Header

    messageID = strings.TrimSpace(h.Get("Message-ID"))
    inReplyTo = strings.TrimSpace(h.Get("In-Reply-To"))
    references = strings.TrimSpace(h.Get("References"))
    replyTo = strings.TrimSpace(h.Get("Reply-To"))
    to = strings.TrimSpace(h.Get("To"))
    cc = strings.TrimSpace(h.Get("Cc"))
    deliveredTo = strings.TrimSpace(h.Get("Delivered-To"))
    xOriginalTo = strings.TrimSpace(h.Get("X-Original-To"))
    envelopeTo = strings.TrimSpace(h.Get("Envelope-To"))
    xEnvelopeTo = strings.TrimSpace(h.Get("X-Envelope-To"))

    return messageID, inReplyTo, references, replyTo, to, cc, deliveredTo, xOriginalTo, envelopeTo, xEnvelopeTo, nil
}

func decodeHeader(s string) string {
    if s == "" {
        return s
    }

    d := &mime.WordDecoder{
        CharsetReader: func(charset string, input io.Reader) (io.Reader, error) {
            switch strings.ToLower(charset) {
            case "utf-8", "us-ascii":
                return input, nil
            case "windows-1251", "cp1251":
                return charmap.Windows1251.NewDecoder().Reader(input), nil
            case "koi8-r":
                return charmap.KOI8R.NewDecoder().Reader(input), nil
            default:
                return nil, fmt.Errorf("unsupported charset: %s", charset)
            }
        },
    }

    decoded, err := d.DecodeHeader(s)
    if err == nil {
        return decoded
    }

    return s
}

func resolveRecipient(email *Email, mailbox string) {
    // Приоритет: Delivered-To > X-Original-To > Envelope-To > X-Envelope-To > To > Cc
    
    if email.DeliveredTo != "" {
        addresses := parseAddressesFromHeader(email.DeliveredTo)
        for _, addr := range addresses {
            if strings.EqualFold(addr, mailbox) {
                email.RecipientEmail = addr
                email.RecipientSource = "Delivered-To"
                email.IsPrimaryRecipient = true
                return
            }
        }
    }
    
    if email.XOriginalTo != "" {
        addresses := parseAddressesFromHeader(email.XOriginalTo)
        for _, addr := range addresses {
            if strings.EqualFold(addr, mailbox) {
                email.RecipientEmail = addr
                email.RecipientSource = "X-Original-To"
                email.IsPrimaryRecipient = true
                return
            }
        }
    }
    
    if email.EnvelopeTo != "" {
        addresses := parseAddressesFromHeader(email.EnvelopeTo)
        for _, addr := range addresses {
            if strings.EqualFold(addr, mailbox) {
                email.RecipientEmail = addr
                email.RecipientSource = "Envelope-To"
                email.IsPrimaryRecipient = true
                return
            }
        }
    }
    
    if email.To != "" {
        addresses := parseAddressesFromHeader(email.To)
        for _, addr := range addresses {
            if strings.EqualFold(addr, mailbox) {
                email.RecipientEmail = addr
                email.RecipientSource = "To"
                email.IsPrimaryRecipient = true
                return
            }
        }
    }
    
    if email.Cc != "" {
        addresses := parseAddressesFromHeader(email.Cc)
        for _, addr := range addresses {
            if strings.EqualFold(addr, mailbox) {
                email.RecipientEmail = addr
                email.RecipientSource = "Cc"
                email.IsPrimaryRecipient = false
                return
            }
        }
    }
    
    email.IsPrimaryRecipient = false
    email.RecipientSource = "unknown"
}

func parseAddressesFromHeader(header string) []string {
    if header == "" {
        return nil
    }
    
    var addresses []string
    parts := strings.Split(header, ",")
    for _, part := range parts {
        part = strings.TrimSpace(part)
        if part == "" {
            continue
        }
        
        addr, err := mail.ParseAddress(part)
        if err != nil {
            if email := extractEmailFromString(part); email != "" {
                addresses = append(addresses, email)
            }
            continue
        }
        addresses = append(addresses, strings.ToLower(strings.TrimSpace(addr.Address)))
    }
    
    return addresses
}

func extractEmailFromString(s string) string {
    re := regexp.MustCompile(`[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}`)
    match := re.FindString(s)
    return strings.ToLower(match)
}

func ParseMessage(uid imap.UID, fetchCmd *imapclient.FetchCommand, mailbox string) (*Email, error) {
	msg := fetchCmd.Next()
	if msg == nil {
		if err := fetchCmd.Close(); err != nil {
			return nil, fmt.Errorf("uid=%d: fetch failed: %w", uid, err)
		}

		return nil, fmt.Errorf("uid=%d: fetch returned no message data", uid)
	}

	defer func() {
		if err := fetchCmd.Close(); err != nil {
			log.Printf("uid=%d: fetch close error: %v", uid, err)
		}
	}()

	email := &Email{
		UID:     uid,
		Mailbox: mailbox,
	}

	var bodyError error

	hasEnvelope := false
	hasHeaderSection := false
	hasBodySection := false
	hasBodyLiteral := false

	for {
		item := msg.Next()
		if item == nil {
			break
		}

		if env, ok := item.(imapclient.FetchItemDataEnvelope); ok {
			hasEnvelope = true

			email.Subject = decodeHeader(env.Envelope.Subject)
			email.From = joinAddresses(env.Envelope.From)

			if !env.Envelope.Date.IsZero() {
				email.Date = env.Envelope.Date.Format(time.RFC3339)
			} else {
				email.Date = ""
			}

			email.MessageID = strings.TrimSpace(env.Envelope.MessageID)
			if len(env.Envelope.InReplyTo) > 0 {
				email.InReplyTo = strings.TrimSpace(env.Envelope.InReplyTo[0])
			}
			email.ReplyTo = firstAddress(env.Envelope.ReplyTo)

			continue
		}

		if bodyData, ok := item.(imapclient.FetchItemDataBodySection); ok {
			section := bodyData.Section
			isHeader := section != nil && section.Specifier == imap.PartSpecifierHeader

			if isHeader {
				if bodyData.Literal != nil {
					hasHeaderSection = true

					msgID, inReplyTo, refs, replyTo, to, cc, deliveredTo,
						xOriginalTo, envelopeTo, xEnvelopeTo, err := parseHeaderFields(bodyData.Literal)
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
					email.To = to
					email.Cc = cc
					email.DeliveredTo = deliveredTo
					email.XOriginalTo = xOriginalTo
					email.EnvelopeTo = envelopeTo
					email.XEnvelopeTo = xEnvelopeTo

					log.Printf("To: %s", email.To)
					log.Printf("Cc: %s", email.Cc)
					log.Printf("Delivered-To: %s", email.DeliveredTo)

					resolveRecipient(email, email.Mailbox)
					log.Printf("RecipientEmail: %s, Source: %s, IsPrimary: %v",
						email.RecipientEmail, email.RecipientSource, email.IsPrimaryRecipient)
				}

				continue
			}

			hasBodySection = true

			if bodyData.Literal != nil {
				hasBodyLiteral = true

				if err := parseBody(email, bodyData.Literal); err != nil {
					bodyError = err
				}
			}

			continue
		}
	}

	log.Printf(
		"uid=%d fetch summary | envelope=%v header=%v body_section=%v body_literal=%v body_len=%d attachments=%d",
		uid,
		hasEnvelope,
		hasHeaderSection,
		hasBodySection,
		hasBodyLiteral,
		len(strings.TrimSpace(email.Body)),
		len(email.Files),
	)

	return email, bodyError
}

func cleanBodyText(body string) string {
    // 1. Убираем явный CSS/HTML‑мусор, но не контент
    lines := strings.Split(body, "\n")
    cleaned := make([]string, 0, len(lines))

    prevEmpty := false

    for _, raw := range lines {
        line := strings.TrimRight(raw, " \t\r")
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

        lower := strings.ToLower(trimmed)
        if strings.Contains(lower, "blockquote.rt") ||
            strings.HasPrefix(lower, "p {") ||
            strings.Contains(lower, ".email-signature") {
            continue
        }

        trimmed = imagePlaceholderRe.ReplaceAllString(trimmed, "")
        trimmed = strings.TrimSpace(trimmed)

        if trimmed == "" {
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

func isInlinePart(contentType, disposition, contentID string) bool {
    ctLower := strings.ToLower(contentType)
    dispLower := strings.ToLower(disposition)

    if strings.Contains(dispLower, "inline") {
        return true
    }

    if contentID != "" && !strings.Contains(dispLower, "attachment") {
        return true
    }

    if strings.HasPrefix(ctLower, "image/") && contentID != "" {
        return true
    }

    return false
}

func parseBody(email *Email, literal io.Reader) error {
    mr, err := msgmail.CreateReader(literal)

    if err != nil &&
        !message.IsUnknownCharset(err) &&
        !message.IsUnknownEncoding(err) {
        return fmt.Errorf("parsing body: %w", err)
    }

    if err != nil {
        log.Printf(
            "UID=%d: MIME reader warning, continuing parsing: %v",
            email.UID,
            err,
        )
    }

    if mr == nil {
        return fmt.Errorf("UID=%d: MIME reader is nil", email.UID)
    }

    var plainParts []string
    var htmlParts []string
    var nestedAttachments []Attachment
    var htmlProcessed bool
    var attachmentIndex int

    for {
        p, err := mr.NextPart()

        if err == io.EOF {
            break
        }

        if err != nil &&
            !message.IsUnknownCharset(err) &&
            !message.IsUnknownEncoding(err) {
            return fmt.Errorf(
                "UID=%d: reading MIME part: %w",
                email.UID,
                err,
            )
        }

        if err != nil {
            log.Printf(
                "UID=%d: MIME part warning, continuing parsing: %v",
                email.UID,
                err,
            )
        }

        if p == nil {
            continue
        }

        contentType := p.Header.Get("Content-Type")
        disposition := p.Header.Get("Content-Disposition")
        contentID := strings.TrimSpace(p.Header.Get("Content-ID"))

        mediaType, _, parseTypeErr := mime.ParseMediaType(contentType)
        if parseTypeErr != nil {
            mediaType = strings.ToLower(strings.TrimSpace(
                strings.Split(contentType, ";")[0],
            ))
        }

        mediaType = strings.ToLower(mediaType)

        log.Printf(
            "UID=%d: MIME part header_type=%T content_type=%q disposition=%q content_id=%q",
            email.UID,
            p.Header,
            contentType,
            disposition,
            contentID,
        )

        // Вложенное письмо (.eml): не сохраняем как файл
        // Извлекаем текст и обычные файлы из него рекурсивно.
        if mediaType == "message/rfc822" {
            nestedBytes, readErr := io.ReadAll(p.Body)
            if readErr != nil {
                return fmt.Errorf(
                    "UID=%d: read nested message: %w",
                    email.UID,
                    readErr,
                )
            }

            if len(nestedBytes) == 0 {
                continue
            }

            nestedText, nestedFiles := extractNestedMessage(nestedBytes)

            if nestedText != "" {
                plainParts = append(
                    plainParts,
                    "--- Пересланное письмо ---\n"+nestedText,
                )
            }

            if len(nestedFiles) > 0 {
                nestedAttachments = append(
                    nestedAttachments,
                    nestedFiles...,
                )
            }

            log.Printf(
                "UID=%d: nested message parsed body_len=%d attachments=%d",
                email.UID,
                len(nestedText),
                len(nestedFiles),
            )

            continue
        }

        // Обычный файл
        if attachmentHeader, ok := p.Header.(*msgmail.AttachmentHeader); ok {
            filename, filenameErr := attachmentHeader.Filename()
            if filenameErr != nil {
                log.Printf(
                    "UID=%d: attachment filename parse warning: %v",
                    email.UID,
                    filenameErr,
                )
            }

            if filename == "" {
                filename = extractFilename(disposition, contentType)
            }

            attachmentIndex++

            if filename == "" {
                filename = fmt.Sprintf(
                    "attachment-%d%s",
                    attachmentIndex,
                    extensionFromContentType(contentType),
                )
            }

            data, readErr := io.ReadAll(p.Body)
            if readErr != nil {
                return fmt.Errorf(
                    "UID=%d: read attachment %q: %w",
                    email.UID,
                    filename,
                    readErr,
                )
            }

            email.Files = append(email.Files, Attachment{
                Name: filename,
                Data: data,
            })

            log.Printf(
                "UID=%d: attachment found name=%q size=%d content_type=%q disposition=%q",
                email.UID,
                filename,
                len(data),
                contentType,
                disposition,
            )

            continue
        }

        // Inline-картинки из HTML: не добавляем ни в Body, ни в Files
        if isInlinePart(contentType, disposition, contentID) {
            if _, err := io.Copy(io.Discard, p.Body); err != nil {
                return fmt.Errorf(
                    "UID=%d: discard inline MIME part: %w",
                    email.UID,
                    err,
                )
            }

            continue
        }

        // Текстовые inline-части письма
        switch mediaType {
        case "text/plain":
            bodyBytes, readErr := io.ReadAll(p.Body)
            if readErr != nil {
                return fmt.Errorf(
                    "UID=%d: read text/plain: %w",
                    email.UID,
                    readErr,
                )
            }

            text := strings.TrimSpace(string(bodyBytes))
            if text != "" {
                plainParts = append(plainParts, text)
            }

        case "text/html":
            bodyBytes, readErr := io.ReadAll(p.Body)
            if readErr != nil {
                return fmt.Errorf(
                    "UID=%d: read text/html: %w",
                    email.UID,
                    readErr,
                )
            }

            htmlStr := string(bodyBytes)

            // Очистить HTML, но оставить таблицы и базовую разметку
            cleaned := sanitizeHTMLKeepTables(htmlStr)

            if cleaned != "" && !htmlProcessed {
                htmlParts = append(htmlParts, cleaned)
                htmlProcessed = true
            }

        default:
            // Полностью дочитываем неизвестную inline-часть перед NextPart
            // Необходимо для корректной работы streaming MIME reader
            if _, err := io.Copy(io.Discard, p.Body); err != nil {
                return fmt.Errorf(
                    "UID=%d: discard unknown MIME part: %w",
                    email.UID,
                    err,
                )
            }
        }
    }

    var body string
    var isHTML bool

    if len(plainParts) > 0 {
        body = strings.Join(plainParts, "\n\n")
        isHTML = false
    } else if len(htmlParts) > 0 {
        body = strings.Join(htmlParts, "\n\n")
        isHTML = true
    }

    email.Files = append(email.Files, nestedAttachments...)

    if isHTML {
        email.Body = strings.TrimSpace(body)
    } else {
        email.Body = cleanBodyText(body)
    }

    log.Printf(
        "UID=%d: body length=%d, plain parts=%d, html parts=%d, attachments=%d",
        email.UID,
        len(email.Body),
        len(plainParts),
        len(htmlParts),
        len(email.Files),
    )

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
        "img": true,
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

// удаляет ненужные части HTML,но оставляет таблицы и базовую разметку
func sanitizeHTMLKeepTables(htmlStr string) string {
    if htmlStr == "" {
        return ""
    }

    doc, err := htmllib.Parse(strings.NewReader(htmlStr))
    if err != nil {
        return htmlStr
    }

    // Теги, которые точно удаляем
    skipTags := map[string]bool{
        "script":   true,
        "style":    true,
        "noscript": true,
        "iframe":   true,
        "object":   true,
        "embed":    true,
        "form":     true,
        "input":    true,
        "link":     true,
        "meta":     true,
        "base":     true,
    }

    var removeNodes []*htmllib.Node

    var walkRemove func(*htmllib.Node)
    walkRemove = func(n *htmllib.Node) {
        if n == nil {
            return
        }

        if n.Type == htmllib.ElementNode && skipTags[n.Data] {
            removeNodes = append(removeNodes, n)
            return
        }

        for c := n.FirstChild; c != nil; c = c.NextSibling {
            walkRemove(c)
        }
    }

    walkRemove(doc)

    for _, n := range removeNodes {
        if n.Parent != nil {
            n.Parent.RemoveChild(n)
        }
    }

    var b strings.Builder
    if err := htmllib.Render(&b, doc); err != nil {
        return htmlStr
    }

    return strings.TrimSpace(b.String())
}

func extractFilename(disposition, contentType string) string {
    var filename string

    if disposition != "" {
        _, params, err := mime.ParseMediaType(disposition)
        if err == nil {
            filename = strings.TrimSpace(params["filename"])
            if filename == "" {
                filename = strings.TrimSpace(params["filename*"])
            }
        }
    }

    if filename == "" && contentType != "" {
        _, params, err := mime.ParseMediaType(contentType)
        if err == nil {
            filename = strings.TrimSpace(params["name"])
        }
    }

    if filename == "" {
        return ""
    }

    filename = decodeHeader(filename)

    filename = strings.Map(func(r rune) rune {
        switch r {
        case '/', '\\', ':', '*', '?', '"', '<', '>', '|':
            return '_'
        }
        return r
    }, filename)

    return filename
}

func extensionFromContentType(contentType string) string {
    mediaType, _, err := mime.ParseMediaType(contentType)
    if err != nil {
        return ""
    }

    switch strings.ToLower(mediaType) {
    case "application/pdf":
        return ".pdf"

    case "application/zip":
        return ".zip"

    case "text/csv":
        return ".csv"

    case "text/plain":
        return ".txt"

    case "text/html":
        return ".html"

    case "text/xml", "application/xml":
        return ".xml"

    case "application/json":
        return ".json"

    case "application/vnd.ms-excel":
        return ".xls"

    case "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        return ".xlsx"

    case "application/msword":
        return ".doc"

    case "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return ".docx"

    case "application/vnd.ms-powerpoint":
        return ".ppt"

    case "application/vnd.openxmlformats-officedocument.presentationml.presentation":
        return ".pptx"

    case "image/jpeg":
        return ".jpg"

    case "image/png":
        return ".png"

    case "image/gif":
        return ".gif"

    case "image/webp":
        return ".webp"

    default:
        return ""
    }
}