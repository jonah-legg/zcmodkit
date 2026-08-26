# Contributing to ZeroCompany ModKit

Thank you for contributing! Before forking, please review below to make sure your pull request has the highest chances of being accepted.

## Guidelines

### Branching

1. Make sure your branch has a descriptive name, it makes it much easier to review.

### Code

1. Run `ruff check .` and `ruff format .` before committing.
2. Type hints are expected on all public functions.
3. Keep docstrings relatively short, preferably one line for simple methods, a brief statement for anything non-obvious.

### Adding a New Domain

If you are exposing a new category of game data (e.g. maps, missions), make sure to do the following:

1. Add a module under `domains/`
2. Expose it on the `Mod` object so users get `mod.yourdomain.target.method()` access.
3. Update the README to include this new functionality.

### Testing

Please make sure you are properly creating tests for your methods. Every method is different, so there isn't a set test coverage or number of tests required, but don't submit a pull request with a bunch of new methods and no tests.

### Submitting a Pull Request

1. Make sure all unit tests pass
2. Open a PR against `main` with a clear description of what and why

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see LICENSE).
