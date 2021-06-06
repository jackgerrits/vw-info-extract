import sys
import clang.cindex
import subprocess
import shlex
import collections
from clang.cindex import CursorKind

from typing import Callable, Deque, Tuple, List, Optional

NodePredicate = Callable[[clang.cindex.Cursor], bool]


def print_node(node: clang.cindex.Cursor, indent: int = 0) -> None:
    print(
        f"{' '*indent}{node.spelling} [line={ node.location.line}, col={node.location.column}], {node.kind}")


def print_tree(node: clang.cindex.Cursor, pred: NodePredicate = None, starting_indent: int = 0, indent_width: int = 2) -> None:
    if (pred is not None and pred(node)) or pred is None:
        print_node(node, indent=starting_indent)

    for c in node.get_children():
        print_tree(c, pred=pred, starting_indent=starting_indent+indent_width)


def find_first_dfs(node: clang.cindex.Cursor, pred: NodePredicate) -> Optional[clang.cindex.Cursor]:
    for c in node.get_children():
        if pred(c):
            return c

        current = find_first_dfs(c, pred)
        if current != None:
            return current

    return None


def find_first_bfs(node: clang.cindex.Cursor, pred: NodePredicate,  debug: bool = False) -> Optional[clang.cindex.Cursor]:
    to_visit: Deque[Tuple[clang.cindex.Cursor, int]
                    ] = collections.deque([(node, 0)])
    while len(to_visit) != 0:
        current, indent = to_visit.popleft()
        if debug:
            print_node(current, indent)

        if pred(current):
            return current

        for c in current.get_children():
            to_visit.append((c, indent+1))

    return None


def find_all(node: clang.cindex.Cursor, pred: NodePredicate) -> List[clang.cindex.Cursor]:
    results: List[clang.cindex.Cursor] = []
    for c in node.get_children():
        if pred(c):
            results.append(c)
        results.extend(find_all(c, pred))
    return results


def is_name_and_kind(name: str, kind: CursorKind) -> NodePredicate:
    return lambda node: name == node.spelling and node.kind == kind


def handle_parse_args_file(node: clang.cindex.Cursor) -> List[str]:
    results: List[str] = []
    parse_reductions_decls = find_all(node, is_name_and_kind(
        "parse_reductions", CursorKind.FUNCTION_DECL))
    for parse_reductions_decl in parse_reductions_decls:
        push_backs = find_all(parse_reductions_decl, is_name_and_kind(
            "push_back", CursorKind.CALL_EXPR))
        for push_back in push_backs:
            # Each call to push_back should have a single argument.
            reduction_arg = next(push_back.get_arguments())
            # By using the tokens we get the raw templated setup functions too.
            results.append(
                "".join(map(lambda tok: tok.spelling, reduction_arg.get_tokens())))
    return results


def handle_setup_fn(node: clang.cindex.Cursor) -> None:
    found = find_first_bfs(node, is_name_and_kind(
        "set_prediction_type", CursorKind.CALL_EXPR))
    if found:
        for arg in found.get_arguments():
            enum_type = arg.type.spelling
            enum_value = arg.spelling
            print(f"prediction type: {enum_type}::{enum_value}")
    else:
        print("Failed to find prediction type")

    found = find_first_bfs(node, is_name_and_kind(
        "set_label_type", CursorKind.CALL_EXPR))
    if found:
        for arg in found.get_arguments():
            enum_type = arg.type.spelling
            enum_value = arg.spelling
            print(f"prediction type: {enum_type}::{enum_value}")
    else:
        print("Failed to find label type")

    add_calls = find_all(node, is_name_and_kind("add", CursorKind.CALL_EXPR))
    for add_call in add_calls:
        for arg in add_call.get_arguments():
            necessary_call = find_first_bfs(
                arg, is_name_and_kind("necessary", CursorKind.CALL_EXPR))
            if necessary_call is not None:
                mk_option_node = find_first_bfs(
                    add_call, is_name_and_kind("make_option", CursorKind.CALL_EXPR))
                # The zeroth argument to make_option is the option long name
                assert mk_option_node is not None
                argument_zero = next(mk_option_node.get_arguments())
                literal = find_first_bfs(
                    argument_zero, lambda node: node.kind == CursorKind.STRING_LITERAL)
                assert literal is not None
                print(f"Necessary option: {literal.spelling}")


def handle_reduction_file(node: clang.cindex.Cursor, setup_fn_name: str) -> None:
    # Since we're looking for a function that is also in the header we'll get two hits.
    # We should use the second one as the first is just the header declaration.
    found = find_all(node, lambda node: setup_fn_name ==
                     node.spelling and node.kind == CursorKind.FUNCTION_DECL)
    if len(found) != 0:
        assert len(found) >= 2
        handle_setup_fn(found[1])
    else:
        print("Failed to find setup fn node")


def generate_ast(file: str, index: clang.cindex.Index, includes: List[str]) -> clang.cindex.Cursor:
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


def find_files_with_text(text_to_find: str) -> List[str]:
    result = subprocess.check_output(shlex.split(
        f"grep --include=\*.cc --exclude=parse_args.cc -rl 'vowpalwabbit' -e '{text_to_find}'"), encoding='UTF-8')
    return result.splitlines()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Extract useful information from vowpal_wabbit source code. Must be run in vowpal_wabbit repo root.")
    # TODO
    # parser.add_argument('--compile_commands')
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

    # TODO determine includes using compile_commands.json
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
            print(fn)
    elif args.which == "parse_setup":
        for file_name in find_files_with_text(args.name):
            root = generate_ast(file_name, index, includes)
            handle_reduction_file(root, args.name)
