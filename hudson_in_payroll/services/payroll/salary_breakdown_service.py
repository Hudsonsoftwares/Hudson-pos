# -*- coding: utf-8 -*-
import logging
from ..base import BaseStatutoryService

_logger = logging.getLogger(__name__)


class SalaryBreakdownService(BaseStatutoryService):
    """
    Pure Python service responsible for calculating and updating salary component breakdowns
    (Basic, HRA, DA, Allowances) on hr.version contracts during salary revisions.
    Serves as the Single Source of Truth for contract breakdown regeneration.
    """

    def calculate_breakdown(self, contract, target_wage):
        """
        Calculates balanced salary component breakdown for a target wage.
        Returns a dictionary of component values where sum of components == target_wage.
        """
        target_wage = float(target_wage or 0.0)
        if target_wage <= 0.0:
            return {
                'basic_salary': 0.0,
                'hra': 0.0,
                'da': 0.0,
                'travel_allowance': 0.0,
                'meal_allowance': 0.0,
                'medical_allowance': 0.0,
                'other_allowance': 0.0,
                'fixed_allowance': 0.0,
                'breakdown_total': 0.0,
            }

        basic = 0.0
        hra = 0.0
        da = 0.0
        travel = 0.0
        meal = 0.0
        medical = 0.0
        other = 0.0

        if contract:
            base_wage = float(contract.wage or 0.0)
            if base_wage > 0.0 and (contract.basic_salary or contract.hra or contract.da or contract.fixed_allowance):
                # Scale components based on existing contract breakdown ratios
                basic = round(target_wage * (float(contract.basic_salary or 0.0) / base_wage), 2)
                hra = round(target_wage * (float(contract.hra or 0.0) / base_wage), 2)
                da = round(target_wage * (float(contract.da or 0.0) / base_wage), 2)
                travel = round(target_wage * (float(contract.travel_allowance or 0.0) / base_wage), 2)
                meal = round(target_wage * (float(contract.meal_allowance or 0.0) / base_wage), 2)
                medical = round(target_wage * (float(contract.medical_allowance or 0.0) / base_wage), 2)
                other = round(target_wage * (float(contract.other_allowance or 0.0) / base_wage), 2)
            elif hasattr(contract, 'contract_template_id') and contract.contract_template_id and contract.contract_template_id.wage > 0.0:
                tmpl = contract.contract_template_id
                tmpl_wage = float(tmpl.wage or 1.0)
                basic = round(target_wage * (float(tmpl.basic_salary or 0.0) / tmpl_wage), 2)
                hra = round(target_wage * (float(tmpl.hra or 0.0) / tmpl_wage), 2)
                da = round(target_wage * (float(tmpl.da or 0.0) / tmpl_wage), 2)
                travel = round(target_wage * (float(tmpl.travel_allowance or 0.0) / tmpl_wage), 2)
                meal = round(target_wage * (float(tmpl.meal_allowance or 0.0) / tmpl_wage), 2)
                medical = round(target_wage * (float(tmpl.medical_allowance or 0.0) / tmpl_wage), 2)
                other = round(target_wage * (float(tmpl.other_allowance or 0.0) / tmpl_wage), 2)
            else:
                # Standard Default Statutory Structure (50% Basic, 40% HRA of Basic)
                basic = round(target_wage * 0.50, 2)
                hra = round(basic * 0.40, 2)
        else:
            basic = round(target_wage * 0.50, 2)
            hra = round(basic * 0.40, 2)

        # Mathematical Balancing Component (Fixed Allowance absorbs rounding remainder)
        subtotal = basic + hra + da + travel + meal + medical + other
        fixed = round(target_wage - subtotal, 2)
        if fixed < 0.0:
            fixed = 0.0

        return {
            'basic_salary': basic,
            'hra': hra,
            'da': da,
            'travel_allowance': travel,
            'meal_allowance': meal,
            'medical_allowance': medical,
            'other_allowance': other,
            'fixed_allowance': fixed,
            'breakdown_total': basic + hra + da + travel + meal + medical + other + fixed,
        }

    def process_breakdown(self, contract, target_wage, mode='auto_structure', manual_dict=None):
        """
        Determines salary component breakdown dictionary based on distribution mode:
        - 'keep_existing': Preserves stored contract component values without alteration.
        - 'manual_adjust': Uses user-supplied manual component values.
        - 'auto_structure': Automatically regenerates components from structure and balances fixed allowance.
        """
        if mode == 'keep_existing' and contract:
            basic = float(contract.basic_salary or 0.0)
            hra = float(contract.hra or 0.0)
            da = float(contract.da or 0.0)
            travel = float(contract.travel_allowance or 0.0)
            meal = float(contract.meal_allowance or 0.0)
            medical = float(contract.medical_allowance or 0.0)
            other = float(contract.other_allowance or 0.0)
            fixed = float(contract.fixed_allowance or 0.0)
            return {
                'basic_salary': basic,
                'hra': hra,
                'da': da,
                'travel_allowance': travel,
                'meal_allowance': meal,
                'medical_allowance': medical,
                'other_allowance': other,
                'fixed_allowance': fixed,
                'breakdown_total': basic + hra + da + travel + meal + medical + other + fixed,
            }

        if mode in ('manual_adjust', 'copy_current') and manual_dict:
            basic = float(manual_dict.get('basic_salary', 0.0) or 0.0)
            hra = float(manual_dict.get('hra', 0.0) or 0.0)
            da = float(manual_dict.get('da', 0.0) or 0.0)
            travel = float(manual_dict.get('travel_allowance', 0.0) or 0.0)
            meal = float(manual_dict.get('meal_allowance', 0.0) or 0.0)
            medical = float(manual_dict.get('medical_allowance', 0.0) or 0.0)
            other = float(manual_dict.get('other_allowance', 0.0) or 0.0)
            fixed = float(manual_dict.get('fixed_allowance', 0.0) or 0.0)
            return {
                'basic_salary': basic,
                'hra': hra,
                'da': da,
                'travel_allowance': travel,
                'meal_allowance': meal,
                'medical_allowance': medical,
                'other_allowance': other,
                'fixed_allowance': fixed,
                'breakdown_total': basic + hra + da + travel + meal + medical + other + fixed,
            }

        return self.calculate_breakdown(contract, target_wage)

    def apply_breakdown_to_contract(self, contract, target_wage, mode='auto_structure', manual_dict=None):
        """
        Calculates or retrieves component breakdown based on mode and updates the specific hr.version contract record.
        Strictly isolated to the single target contract instance.
        """
        if not contract:
            return False

        if mode == 'keep_existing':
            _logger.info(
                "[SalaryBreakdownService] Mode 'keep_existing': Updating contract wage to %s for Contract %s (Employee %s) without modifying component breakdown.",
                target_wage, contract.name, contract.employee_id.name
            )
            contract.write({'wage': target_wage})
            if hasattr(contract, '_compute_breakdown_totals'):
                contract._compute_breakdown_totals()
            return self.process_breakdown(contract, target_wage, mode='keep_existing')

        breakdown = self.process_breakdown(contract, target_wage, mode=mode, manual_dict=manual_dict)
        _logger.info(
            "[SalaryBreakdownService] Mode '%s': Updating breakdown for Contract %s (Employee %s): Gross %s -> Basic=%s, HRA=%s, DA=%s, Fixed=%s",
            mode, contract.name, contract.employee_id.name, target_wage,
            breakdown['basic_salary'], breakdown['hra'], breakdown['da'], breakdown['fixed_allowance']
        )

        contract.write({
            'wage': target_wage,
            'basic_salary': breakdown['basic_salary'],
            'hra': breakdown['hra'],
            'da': breakdown['da'],
            'travel_allowance': breakdown['travel_allowance'],
            'meal_allowance': breakdown['meal_allowance'],
            'medical_allowance': breakdown['medical_allowance'],
            'other_allowance': breakdown['other_allowance'],
            'fixed_allowance': breakdown['fixed_allowance'],
        })

        if hasattr(contract, '_compute_breakdown_totals'):
            contract._compute_breakdown_totals()

        return breakdown
