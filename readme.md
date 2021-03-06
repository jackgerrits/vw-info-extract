# vw-info-extract

This repo is an experiment of using [Python bindings](https://pypi.org/project/libclang/) for [`libclang`](https://clang.llvm.org/doxygen/group__CINDEX.html) to parse [vowpal_wabbit](https://github.com/VowpalWabbit/vowpal_wabbit) source code into the AST and traverse this to extract useful information about reductions. It is created with the thinking of automatically producing metadata based documentation about all VW reductions.

It is by no means ready in any way, but I wanted to save progress.

It has two commands:
- `list_reductions` - will parse the `parse_args.cc` file and extract the name of each setup function used to create the reduction stack
- `parse_setup` - given a setup function name will search for files which contain it and then attempt to extract several properties of that reduction:
    - prediction type
    - label type
    - necessary option

## Usage

```
usage: main.py [-h] {list_reductions,parse_setup} ...

Extract useful information from vowpal_wabbit source code. Must be run in vowpal_wabbit repo root.

positional arguments:
  {list_reductions,parse_setup}
    list_reductions     Outputs the all reduction setup function names
    parse_setup         Extract info of one reduction

optional arguments:
  -h, --help            show this help message and exit
```

## Known issues
- `parse_setup` only works for reductions with a unique symbol name, as you cannot specify using namespaces
- `parse_setup` only understands reductions using the `make_reduction_learner` style interface
