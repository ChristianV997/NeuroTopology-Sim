import argparse

from sciencer_d.btc_icft.simulations.validation_runner import run_synthetic_validation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run_synthetic_validation(args.out)


if __name__ == "__main__":
    main()
