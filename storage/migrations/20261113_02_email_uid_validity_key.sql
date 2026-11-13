BEGIN;

SET LOCAL lock_timeout = '5s';

ALTER TABLE public.emails
    ADD CONSTRAINT emails_mailbox_uid_validity_uid_key
    UNIQUE NULLS NOT DISTINCT (
        mailbox,
        uid_validity,
        email_uid
    );

ALTER TABLE public.emails
    DROP CONSTRAINT emails_mailbox_email_uid_key;

COMMIT;