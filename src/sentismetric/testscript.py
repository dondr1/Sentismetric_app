from sentismetric.log import setup_logging, log
setup_logging(level="INFO")
log.debug("This is a DEBUG message (should NOT appear)")
log.info("This is an INFO message (should appear)")
log.warning("This is a WARNING message (should appear)")