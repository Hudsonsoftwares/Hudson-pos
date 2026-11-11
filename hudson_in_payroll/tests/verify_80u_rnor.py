import logging
_logger = logging.getLogger(__name__)

# -*- coding: utf-8 -*-
import py_compile

_logger.info("Compiling Section 80U RNOR verification files...")
py_compile.compile("services/tds/resident_validation_service.py")
py_compile.compile("services/tds/section_80u_deduction_service.py")
py_compile.compile("tests/test_section_80u_engine.py")
_logger.info("Compiled successfully!")
