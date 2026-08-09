begin;

alter table settlement.courier_settlement_adjustment
    drop constraint if exists courier_settlement_adjustment_adjustment_type_check;

alter table settlement.courier_settlement_adjustment
    add constraint courier_settlement_adjustment_adjustment_type_check
    check (
        adjustment_type in (
            'bonus',
            'malus',
            'atm_deduction',
            'other_expense',
            'customer_rating',
            'correction',
            'manual_correction',
            'correction_income',
            'correction_deduction',
            'manual_correction_deduction'
        )
    );

commit;
