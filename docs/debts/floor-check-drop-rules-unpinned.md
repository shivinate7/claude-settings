# Floor check drop rules have no case per branch

**What.** The `IntMemberReceiver` case pins only what stays dropped. `(x / 2.0).is_integer()` hits two BinOp branches at once, so neither branch is tested alone. Five mutants kept all seven tests in `FloatMember` and `IntMemberReceiver` green: dropping the `ast.Div` branch, dropping the non-int `Constant` branch, dropping the container tuple, dropping the comprehension `range` binding, and dropping the class-base and decorator visits.

**Where.** `lint/test_check_python_floor.py`: `FLOAT_DIVIDE` (:923) and `IntMemberReceiver.test_float_quotient_is_integer_is_not_flagged` (:955). `lint/check_python_floor.py`: `is_not_int_expression`, `IntMembers.visit_comprehension` and `IntMembers.visit_ClassDef`.

**Decision.** `ci-pins-newest-interpreter`: the CI pin decision. It keeps the 3.9 floor for product code, checked by `lint/check_python_floor.py`.

**Retire.** One case per branch, each red when its branch is removed: the `Div` branch, the non-int `Constant` branch, the container tuple, the comprehension `range` binding, and the class-base and decorator visits. `lint/test_check_python_floor.py` runs it.
