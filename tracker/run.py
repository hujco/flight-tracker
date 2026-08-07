import logging
import os
import sys
from datetime import datetime, timezone

from . import collect, config, db, notify, report


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(str(config.LOG_PATH)),
            # bez stdout je zlyhanie v GitHub Actions neviditeľné: log súbor je
            # v .gitignore a s runnerom zanikne
            logging.StreamHandler(sys.stdout),
        ],
    )
    # UTC explicitne: to isté beží aj lokálne (launchd), kde by naivný čas bol CEST
    observed_at = datetime.now(timezone.utc).isoformat(timespec="minutes")
    conn = db.connect(config.DB_PATH)
    db.init_db(conn)

    collect_failed = None
    try:
        n = collect.collect_once(conn, observed_at)
        logging.info("collected %d rows at %s", n, observed_at)
    except Exception as exc:  # zlyhanie zberu -> nic sa nezapise (atomicita),
        collect_failed = exc                                          # report sa aj tak pregeneruje z existujucich dat
        logging.error("collect failed at %s: %s", observed_at, exc)

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
        sent, msg = notify.maybe_notify(rows, conn=conn)
        logging.info("notify: %s", msg)
    except Exception as exc:  # alert nesmie zhodiť beh
        logging.error("notify failed: %s", exc)

    # Report a alert prebehli aj tak, ale beh musí skončiť červeno — inak je
    # „zelený beh, ktorý nezapísal nič" na nerozoznanie od úspechu.
    if collect_failed is not None:
        raise SystemExit(f"zber zlyhal: {collect_failed}")


if __name__ == "__main__":
    main()
