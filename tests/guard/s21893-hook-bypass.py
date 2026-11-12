# section 21893
FAMILY = "hook-bypass"


def mutate_shared_hooks_path_case():
    """Scope first: the file has a _make_checkout function. Then the subject: one call in it runs `worktree add`
    with a core.hooksPath setting. The file is read with ast, so a comment or a docstring that names the key
    does not count."""
    path = os.path.join(REPO, "hooks", "mutate_shared.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), path)
    funcs = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_make_checkout"]
    if not funcs:
        return False, "hooks/mutate_shared.py has no _make_checkout function"
    for call in (node for node in ast.walk(funcs[0]) if isinstance(node, ast.Call)):
        texts = [part.value for part in ast.walk(call)
                 if isinstance(part, ast.Constant) and isinstance(part.value, str)]
        if "worktree" in texts and "add" in texts and any(text.startswith("core.hooksPath=") for text in texts):
            return True, "_make_checkout's worktree add sets core.hooksPath"
    return False, "_make_checkout's worktree add no longer sets core.hooksPath"


LOG_CHECKS_EXTRA.append(("hook-bypass: hooks/mutate_shared.py still sets core.hooksPath in the checkout it makes",
                         mutate_shared_hooks_path_case))
FIXTURELESS_CHECKS.add(mutate_shared_hooks_path_case)

# ---- frozen: the main mirror and the live pin name are copied into guard_frozen.py from install.sh and
# merge/install_from_main.sh. Each shell name is a literal in its script, and the guard keeps its own copy
# (MAIN_MIRROR_NAME, LIVE_PIN_SUFFIX). Each copy is read as text, never imported, so the check loads no guard.
# A change to one side alone would leave the frozen check guarding a folder that no install builds.
