import logging
_logger = logging.getLogger(__name__)

# -*- coding: utf-8 -*-
import py_compile

_logger.info("Compiling deduction_calculation_service.py...")
py_compile.compile("services/tds/deduction_calculation_service.py")
py_compile.compile("tests/test_section_80u_engine.py")
_logger.info("Compiled successfully!")
