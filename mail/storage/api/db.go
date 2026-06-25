package api

import (
	"database/sql"
	"fmt"

	"mail/storage/configdb"

	_ "github.com/lib/pq"
)

type DB struct {
	Conn *sql.DB
}

func ConnectPostgres(cfg *configdb.Config) (*DB, error) {
	dsn := fmt.Sprintf(
		"host=%s port=%d user=%s password=%s dbname=%s sslmode=disable",
		cfg.Host, cfg.Port, cfg.User, cfg.Password, cfg.Name,
	)

	db, err := sql.Open("postgres", dsn)
	if err != nil {
		return nil, err
	}
	if err := db.Ping(); err != nil {
		return nil, err
	}
	return &DB{Conn: db}, nil
}
