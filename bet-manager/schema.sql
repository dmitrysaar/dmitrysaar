CREATE TABLE matches (
id INTEGER PRIMARY KEY AUTOINCREMENT,
match_date DATE NOT NULL,
tournament VARCHAR(100) NOT NULL,
team1 VARCHAR(100) NOT NULL,
team2 VARCHAR(100) NOT NULL
, match_result TEXT);

CREATE TABLE bets (
id INTEGER PRIMARY KEY AUTOINCREMENT,
match_id INT NOT NULL,
bet_type VARCHAR(100) NOT NULL,
bet_amount DECIMAL (10,2) NOT NULL,
coefficient DECIMAL (5,2) NOT NULL,
win_or_loss DECIMAL (10,2) NOT NULL, bettor_id integer,
FOREIGN KEY (match_id) REFERENCES matches(id)
);

CREATE TABLE bettor (
id integer primary key autoincrement,
nickname varchar(100) not null);