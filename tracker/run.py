import logging
import os
from datetime import datetime

from . import collect, config, db, notify, report


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
    except Exception as exc:  # zlyhanie zberu -> nic sa nezapise (atomicita),
        logging.error("collect failed at %s: %s", observed_at, exc)  # report sa aj tak pregeneruje z existujucich dat

    # report vzdy pregeneruj z aktualnych dat v DB (aj ked tento zber zlyhal)
    rows = db.all_rows(conn)
    report.write_report(rows, config.REPORT_PATH)
    logging.info("report written to %s (%d total rows)", config.REPORT_PATH, len(rows))

    if os.environ.get("ALERT_TEST", "").lower() in ("1", "true", "yes"):
        try:
            _, msg = notify.send_test()
            logging.info("notify test: %s", msg)
        except Exception as exc:
            logging.error("notify test failed: %s", exc)

    try:
        sent, msg = notify.maybe_notify(rows)
        logging.info("notify: %s", msg)
    except Exception as exc:  # alert nesmie zhodiť beh
        logging.error("notify failed: %s", exc)


if __name__ == "__main__":
    main()
