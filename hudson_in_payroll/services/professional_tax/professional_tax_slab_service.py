# -*- coding: utf-8 -*-
import logging
# pyrefly: ignore [missing-import]
from odoo import fields
from ..payroll.work_location_service import PayrollWorkLocationService

_logger = logging.getLogger(__name__)


class ProfessionalTaxSlabResult:
    """
    Structured Result Container representing an applicable Professional Tax Slab resolution.
    Encapsulates all statutory properties of a matching pt.state.slab record without calculation logic.
    """

    def __init__(self, slab_record):
        self.slab_record = slab_record
        self.state = slab_record.state_id
        self.company = slab_record.company_id
        self.salary_from = slab_record.salary_from
        self.salary_to = slab_record.salary_to
        self.pt_amount = slab_record.pt_amount
        self.periodicity = slab_record.periodicity
        self.override_month = slab_record.override_month
        self.override_amount = slab_record.override_amount
        self.date_from = slab_record.date_from
        self.date_to = slab_record.date_to
        self.special_rules = slab_record.special_rules
        self.notification_ref = slab_record.notification_ref
        self.remarks = slab_record.remarks

    def to_dict(self):
        """Returns a structured dictionary representation of the resolved slab."""
        return {
            'state_id': self.state.id if self.state else False,
            'state_name': self.state.name if self.state else False,
            'company_id': self.company.id if self.company else False,
            'company_name': self.company.name if self.company else False,
            'salary_from': self.salary_from,
            'salary_to': self.salary_to,
            'pt_amount': self.pt_amount,
            'periodicity': self.periodicity,
            'override_month': self.override_month,
            'override_amount': self.override_amount,
            'date_from': str(self.date_from) if self.date_from else False,
            'date_to': str(self.date_to) if self.date_to else False,
            'special_rules': self.special_rules,
            'notification_ref': self.notification_ref,
            'remarks': self.remarks,
        }

    def __repr__(self):
        return (
            f"<ProfessionalTaxSlabResult state={self.state.name if self.state else None} "
            f"salary_range=[{self.salary_from}-{self.salary_to}] pt_amount={self.pt_amount} "
            f"periodicity={self.periodicity}>"
        )


class ProfessionalTaxSlabService:
    """
    Domain Service for resolving the applicable Professional Tax (PT) State Slab.
    Decoupled from eligibility validation, calculation math, payslips, and salary rules.

    Responsibilities:
    - Locate the matching pt.state.slab master configuration using:
      1. Employee Statutory Work State (resolved via PayrollWorkLocationService)
      2. Employee Company Scope
      3. Monthly Gross / Taxable Salary Amount
      4. Payroll Evaluation Date (effective-dated lookup)
      5. Employee Gender Applicability
      6. Active Record Status
    - Return a structured ProfessionalTaxSlabResult object (or None if no match found).
    """

    def __init__(self, env):
        self.env = env
        self.location_service = PayrollWorkLocationService(env)

    @staticmethod
    def resolve_employee_gender(employee):
        """
        Centralized helper for resolving and normalizing an employee's gender.
        Reads `employee.sex` (standard Odoo 19 hr.employee field),
        with fallback to `employee.gender` if present.
        Returns 'male', 'female', 'other', or None if unavailable.
        """
        if not employee:
            return None
        raw_val = getattr(employee, 'sex', None) or getattr(employee, 'gender', None)
        if not raw_val:
            return None
        val_str = str(raw_val).strip().lower()
        if val_str in ('m', 'male'):
            return 'male'
        elif val_str in ('f', 'female'):
            return 'female'
        elif val_str in ('o', 'other'):
            return 'other'
        return val_str

    def resolve_state_periodicity(self, state, company=None):
        """
        Resolves the primary PT periodicity for a state from active pt.state.slab records.
        Defaults to 'monthly' if unassigned or no slabs exist.
        """
        if not state:
            return 'monthly'
        domain = [('state_id', '=', state.id), ('active', '=', True)]
        if company:
            domain += ['|', ('company_id', '=', False), ('company_id', '=', company.id)]
        slabs = self.env['pt.state.slab'].search(domain, limit=1)
        return slabs.periodicity if slabs else 'monthly'

    def get_applicable_slab(self, employee=None, salary=0.0, eval_date=None, company=None, state=None, gender=None, periodicity=None):
        """
        Retrieves the single applicable Professional Tax slab for an employee or salary scenario.
        Uses a data-driven 2-stage lookup strategy and filters by periodicity.

        :param employee: hr.employee recordset (optional if state is passed)
        :param salary: float (supplied monthly or aggregated gross salary amount)
        :param eval_date: datetime.date or str (defaults to today if omitted)
        :param company: res.company recordset (optional company scope)
        :param state: res.country.state recordset (optional explicit state override)
        :param gender: str ('male', 'female', 'other', 'all' - resolved from employee if omitted)
        :param periodicity: str ('monthly', 'half_yearly', 'quarterly', 'annual' - resolved from state if omitted)
        :return: ProfessionalTaxSlabResult instance or None
        """
        try:
            salary = float(salary or 0.0)
        except (TypeError, ValueError):
            salary = 0.0

        # 1. Resolve Statutory Work State
        target_state = state
        if not target_state and employee:
            target_state = self.location_service.get_work_state(employee)

        if not target_state:
            _logger.info("ProfessionalTaxSlabService: Work state could not be resolved for employee %s", getattr(employee, 'name', None))
            return None

        # 2. Resolve Company Scope
        target_company = company
        if not target_company and employee:
            target_company = employee.company_id
        if not target_company:
            target_company = self.env.company

        # 3. Resolve Evaluation Date
        if not eval_date:
            eval_date = fields.Date.today()
        elif isinstance(eval_date, str):
            eval_date = fields.Date.from_string(eval_date)

        # 4. Resolve Gender Criteria via Centralized Helper
        target_gender = gender or self.resolve_employee_gender(employee)

        # 5. Resolve Periodicity Criteria
        target_periodicity = periodicity or self.resolve_state_periodicity(target_state, company=target_company)

        # 6. Build Base Search Domain
        base_domain = [
            ('state_id', '=', target_state.id),
            ('active', '=', True),
            ('salary_from', '<=', salary),
            '|', ('salary_to', '=', False), ('salary_to', '>=', salary),
            '|', ('date_from', '=', False), ('date_from', '<=', eval_date),
            '|', ('date_to', '=', False), ('date_to', '>=', eval_date),
            '|', ('company_id', '=', False), ('company_id', '=', target_company.id),
        ]
        if target_periodicity:
            base_domain.append(('periodicity', '=', target_periodicity))

        # Phase A: Gender-Specific Search (e.g. Maharashtra Male/Female Slabs)
        if target_gender and target_gender != 'all':
            domain_specific = base_domain + [('gender', '=', target_gender)]
            slabs_specific = self.env['pt.state.slab'].search(domain_specific)
            if slabs_specific:
                best_slab = self._select_best_slab(slabs_specific, target_company, target_gender, eval_date)
                if best_slab:
                    return ProfessionalTaxSlabResult(best_slab)

        # Phase B: Fallback Search for 'all' / Unspecified Gender Slabs (e.g. Kerala, Karnataka, Gujarat, AP)
        domain_all = base_domain + [('gender', '=', 'all')]
        slabs_all = self.env['pt.state.slab'].search(domain_all)
        if slabs_all:
            best_slab = self._select_best_slab(slabs_all, target_company, 'all', eval_date)
            if best_slab:
                return ProfessionalTaxSlabResult(best_slab)

        # Phase C: No Matching Slab Found
        _logger.info(
            "ProfessionalTaxSlabService: No active PT slab found for state '%s', company '%s', salary %s, gender %s on date %s",
            target_state.name, target_company.name, salary, target_gender or 'all', eval_date
        )
        return None

    def _select_best_slab(self, slabs, company, gender, eval_date):
        """
        Ranks matching slabs by specificity:
        1. Company-specific slab over global slab
        2. Exact gender match over 'all' gender
        3. Most recent date_from
        """
        def rank_key(s):
            is_company = 1 if (company and s.company_id and s.company_id.id == company.id) else 0
            is_exact_gender = 1 if (s.gender and s.gender == gender) else 0
            d_from = s.date_from or fields.Date.from_string('1900-01-01')
            s_from = s.salary_from or 0.0
            return (is_company, is_exact_gender, d_from, s_from, s.id)

        sorted_slabs = sorted(slabs, key=rank_key, reverse=True)
        return sorted_slabs[0] if sorted_slabs else None
