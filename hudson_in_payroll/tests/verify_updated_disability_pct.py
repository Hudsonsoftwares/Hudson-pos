import logging
_logger = logging.getLogger(__name__)

# -*- coding: utf-8 -*-
import py_compile

_logger.info("Compiling Section 80U Updated Disability Percentage verification files...")
py_compile.compile("models/tds_employee_declaration.py")
py_compile.compile("services/tds/section_80u_deduction_service.py")
py_compile.compile("services/tds/chapter6a_deduction_service.py")
py_compile.compile("tests/test_section_80u_engine.py")
_logger.info("Compiled successfully!")
