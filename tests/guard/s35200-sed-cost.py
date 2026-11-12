# section 35200
FAMILY = "frozen"

# The sed operand reader, cost-budget. This section loads after rm_var_ratio (section 35192), which it uses.
# Each case judges 6000 words against 1000 of the same shape, scaled by six, in this process (rm_var_ratio).
# Linear work is a ratio of 1 and a quadratic one is 6, which RM_VAR_K = 3 refuses.


def sed_cost_cmd(n):
    return "sed -i 's/a/b/' " + CFG_HOOK + " " + " ".join("word%d" % i for i in range(n))


def echo_cost_cmd(n):
    return "echo " + " ".join("word%d" % i for i in range(n))


def sed_cost_case():
    return rm_var_ratio(sed_cost_cmd, 1000, 6000, must="frozen-path")


def echo_cost_case():
    return rm_var_ratio(echo_cost_cmd, 1000, 6000, must="", want="allow", cap=1000)


LOG_CHECKS_EXTRA.append(("sed-operand cost-budget: a 6000-word sed -i onto a frozen hook scales linearly in CPU",
                         sed_cost_case))
LOG_CHECKS_EXTRA.append(("sed-operand cost-budget: a 6000-word plain echo scales linearly in CPU",
                         echo_cost_case))
