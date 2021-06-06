import sys
import clang.cindex
import subprocess
import shlex
import collections
from clang.cindex import CursorKind


def print_node(node, indent=0):
    print(
        f"{' '*indent}{node.spelling} [line={ node.location.line}, col={node.location.column}], {node.kind}")


def print_tree(node, pred=None, starting_indent=0, indent_width=2):
    if (pred is not None and pred(node)) or pred is None:
        print_node(node, indent=starting_indent)

    for c in node.get_children():
        print_tree(c, pred=pred, starting_indent=starting_indent+indent_width)


def find_first_dfs(node, pred):
    for c in node.get_children():
        if pred(c):
            return c

        current = find_first_dfs(c)
        if current != None:
            return current

    return None


def find_first_bfs(node, pred, debug=False):
    to_visit = collections.deque([(node, 0)])
    while len(to_visit) != 0:
        current, indent = to_visit.popleft()
        if debug:
            print_node(current, indent)

        if pred(current):
            return current

        for c in current.get_children():
            to_visit.append((c, indent+1))

    return None


def find_all(node, pred):
    results = []
    for c in node.get_children():
        if pred(c):
            results.append(c)
        results.extend(find_all(c, pred))
    return results


def get_enum_type(node):
    for c in node.get_children():
        if c.kind == CursorKind.DECL_REF_EXPR:
            return to_qualified_name(c)


def is_name_and_kind(name, kind):
    return lambda node: name == node.spelling and node.kind == kind


def handle_parse_args_file(node):
    results = []
    parse_reductions_decls = find_all(node, is_name_and_kind(
        "parse_reductions", CursorKind.FUNCTION_DECL))
    for parse_reductions_decl in parse_reductions_decls:
        push_backs = find_all(parse_reductions_decl, is_name_and_kind(
            "push_back", CursorKind.CALL_EXPR))
        for push_back in push_backs:
            for reduction_arg in find_all(push_back, lambda node: node.spelling != "reductions" and node.kind == CursorKind.DECL_REF_EXPR):
                results.append(to_qualified_name(reduction_arg))
    return results


def to_qualified_name(node):
    assert node.kind == CursorKind.DECL_REF_EXPR
    name_components = []
    for c in node.get_children():
        offset = 0
        if c.spelling.startswith("enum "):
            offset = 5
        name_components.append(c.spelling[offset:])
    name_components.append(node.spelling)
    return name_components


def handle_setup_fn(node):
    found = find_first_bfs(node, lambda node: "set_prediction_type" ==
                           node.spelling and node.kind == CursorKind.CALL_EXPR)
    if found:
        print(f"prediction type: {'::'.join(get_enum_type(found))}")
    else:
        print("Failed to find prediction type")

    found = find_first_bfs(node, lambda node: "set_label_type" ==
                           node.spelling and node.kind == CursorKind.CALL_EXPR)
    if found:
        print(f"label type: {'::'.join(get_enum_type(found))}")
    else:
        print("Failed to find label type")

    found = find_all(node, lambda node: "add" ==
                     node.spelling and node.kind == CursorKind.CALL_EXPR)

    # The 0th one seems to contain all options. So chop it off?
    if len(found) > 0:
        found = found[1:]

    for f in found:
        # This is a necessary option
        if find_first_bfs(f, lambda node: "necessary" == node.spelling) is not None:
            mk_option_node = find_first_bfs(
                f, lambda node: "make_option" == node.spelling)
            option_name = find_first_bfs(
                mk_option_node, lambda node: node.kind == CursorKind.STRING_LITERAL)
            print(f"Necessary option: {option_name.spelling}")


def handle_reduction_file(node, setup_fn_name):
    # Since we're looking for a function that is also in the header we'll get two hits.
    # We should use the second one as the first is just the header declaration.
    found = find_all(node, lambda node: setup_fn_name ==
                     node.spelling and node.kind == CursorKind.FUNCTION_DECL)
    if len(found) != 0:
        assert(len(found) >= 2)
        handle_setup_fn(found[1])
    else:
        print("Failed to find setup fn node")


def generate_ast(file, index, includes):
    translation_unit = index.parse(file, args=includes)
    found_diag = False
    for diag in translation_unit.diagnostics:
        print(diag)
        found_diag = True

    if found_diag:
        print("Parse errors found.")
        sys.exit(1)

    print('Parsed:', translation_unit.spelling)
    print()
    return translation_unit.cursor


def find_files_with_text(text_to_find):
    result = subprocess.check_output(shlex.split(
        f"grep --include=\*.cc --exclude=parse_args.cc -rl 'vowpalwabbit' -e '{text_to_find}'"))
    return result.splitlines()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Extract useful information from vowpal_wabbit source code. Must be run in vowpal_wabbit repo root.")
    # TODO
    # parser.add_argument('--vw_root')
    subparsers = parser.add_subparsers()
    list_reductions_subparser = subparsers.add_parser(
        "list_reductions", help="Outputs the all reduction setup function names")
    list_reductions_subparser.set_defaults(which='list_reductions')
    parse_setup_subparser = subparsers.add_parser(
        "parse_setup", help="Extract info of one reduction")
    parse_setup_subparser.add_argument(
        'name', help="Setup function name to parse. Note doens't support namespaces yet.")
    parse_setup_subparser.set_defaults(which='parse_setup')

    args = parser.parse_args()

    if not hasattr(args, 'which'):
        parser.print_help()
        sys.exit(0)

    index = clang.cindex.Index.create()

    includes = ["-Ivowpalwabbit",
                "-Ibuild/vowpalwabbit",
                "-Iexplore",
                "-Iext_libs/spdlog/include",
                "-Iext_libs/fmt/include",
                "-Iext_libs/rapidjson/include",
                "-I/usr/lib/clang/10/include"]

    if args.which == "list_reductions":
        root = generate_ast("vowpalwabbit/parse_args.cc", index, includes)
        for fn in handle_parse_args_file(root):
            print("::".join(fn))
    elif args.which == "parse_setup":
        for file_name in find_files_with_text(args.name):
            root = generate_ast(file_name, index, includes)
            handle_reduction_file(root, args.name)
