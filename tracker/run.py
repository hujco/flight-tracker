import logging
from datetime import datetime

from . import collect, config, db, report


def main():
    logging.basicConfig(
        filename=str(config.LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    observed_at = datetime.now().isoformat(timespec="minutes")
    conn = db.connect(config.DB_PATH)
    db.init_db(conn)

    try:
        n = collect.collect_once(conn, observed_at)
        logging.info("collected %d rows at %s", n, observed_at)
    except Exception as exc:  # zlyhanie zberu -> nic nezapisane, skus o hodinu
        logging.error("collect failed at %s: %s", observed_at, exc)
        return

    rows = db.all_rows(conn)
    report.write_report(rows, config.REPORT_PATH)
    logging.info("report written to %s (%d total rows)", config.REPORT_PATH, len(rows))


if __name__ == "__main__":
    main()
