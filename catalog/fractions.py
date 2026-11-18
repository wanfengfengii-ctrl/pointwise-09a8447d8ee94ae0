from fractions import Fraction


def encode_availability(availability: Fraction) -> tuple[str, str]:
    return format(availability.numerator, 'x'), format(availability.denominator, 'x')


def decode_availability(numerator: str, denominator: str) -> Fraction:
    return Fraction(int(numerator, 16), int(denominator, 16))
