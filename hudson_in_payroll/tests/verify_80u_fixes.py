# -*- coding: utf-8 -*-
import logging
import py_compile

_logger = logging.getLogger("verify_80u_fixes")

_logger.info("Compiling Python files for Section 80U...")
py_compile.compile("services/tds/section_80u_deduction_service.py")
py_compile.compile("models/tds_employee_declaration.py")
py_compile.compile("tests/test_section_80u_engine.py")
_logger.info("All Python files compiled successfully!")
