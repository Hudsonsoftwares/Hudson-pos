import logging
_logger = logging.getLogger(__name__)

# -*- coding: utf-8 -*-
import py_compile

_logger.info("Compiling home_loan_deduction_service.py...")
py_compile.compile("services/tds/home_loan_deduction_service.py")
_logger.info("Compiled successfully!")
