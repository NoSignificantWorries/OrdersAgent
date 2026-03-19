CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION create_admin_user(
    in_login  VARCHAR,
    in_email  VARCHAR,
    in_pass   VARCHAR
) RETURNS BIGINT AS $$
DECLARE
    new_id BIGINT;
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE login = in_login) THEN
        RAISE EXCEPTION 'User with login % already exists', in_login;
    END IF;

    IF EXISTS (SELECT 1 FROM users WHERE email = in_email) THEN
        RAISE EXCEPTION 'User with email % already exists', in_email;
    END IF;

    INSERT INTO users (login, email, pass_hash, role)
    VALUES (
        in_login,
        in_email,
        crypt(in_pass, gen_salt('bf')),
        'admin'
    )
    RETURNING id INTO new_id;

    RETURN new_id;
END;
$$ LANGUAGE plpgsql;


