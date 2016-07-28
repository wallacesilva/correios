# Copyright 2016 Osvaldo Santana Neto
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
from datetime import datetime
from typing import Union, Optional, Sequence

from PIL import Image

from correios import DATADIR
from correios.exceptions import (InvalidFederalTaxNumberError, InvalidExtraServiceError,
                                 InvalidRegionalDirectionError, InvalidUserContractError)
from .data import EXTRA_SERVICES, REGIONAL_DIRECTIONS, SERVICES

EXTRA_SERVICE_CODE_SIZE = 2


def to_integer(number: Union[int, str]) -> int:
    try:
        return int(number.strip())
    except AttributeError:
        return int(number)


def to_datetime(date: Union[datetime, str], fmt="%Y-%m-%d %H:%M:%S%z") -> datetime:
    if isinstance(date, str):
        last_colon_pos = date.rindex(":")
        date = date[:last_colon_pos] + date[last_colon_pos + 1:]
        return datetime.strptime(date, fmt)
    return date


def _to_federal_tax_number(federal_tax_number) -> "FederalTaxNumber":
    if isinstance(federal_tax_number, FederalTaxNumber):
        return federal_tax_number

    return FederalTaxNumber(federal_tax_number)


def _to_state_tax_number(state_tax_number) -> "StateTaxNumber":
    if isinstance(state_tax_number, StateTaxNumber):
        return state_tax_number

    return StateTaxNumber(state_tax_number)


class AbstractTaxNumber:
    def __init__(self, number: str):
        self._number = self._validate(number)

    @property
    def number(self) -> str:
        return self._number

    def _sanitize(self, raw_number: str) -> str:
        return "".join(d for d in raw_number if d.isdigit())

    def _validate(self, raw_number: str):
        raise NotImplementedError()  # pragma: no cover

    def display(self) -> str:
        raise NotImplementedError()  # pragma: no cover

    def __str__(self):
        return self.number

    def __repr__(self):
        return "<{} number: {}>".format(self.__class__.__name__, self.number)

    def __eq__(self, other):
        return self.number == self._sanitize(other)


class FederalTaxNumber(AbstractTaxNumber):
    FEDERAL_TAX_NUMBER_SIZE = 14

    def _check_verification_digits(self, raw_number):
        number = [int(d) for d in raw_number[:12]]
        prod = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        assert len(number) == len(prod)

        while len(number) < 14:
            r = sum(x * y for (x, y) in zip(number, prod)) % 11
            f = (11 - r) if r > 1 else 0
            number.append(f)
            prod.insert(0, prod[0] + 1)

        number = "".join(str(d) for d in number)
        return raw_number == number

    def _validate(self, raw_number: str):
        raw_number = self._sanitize(raw_number)

        if len(raw_number) != FederalTaxNumber.FEDERAL_TAX_NUMBER_SIZE:
            raise InvalidFederalTaxNumberError(
                "Tax Number must have {} digits".format(self.FEDERAL_TAX_NUMBER_SIZE))

        if not self._check_verification_digits(raw_number):
            raise InvalidFederalTaxNumberError("Invalid Federal Tax Number verification digits")

        return raw_number

    def display(self) -> str:
        return "{}.{}.{}/{}-{}".format(self.number[:2],
                                       self.number[2:5],
                                       self.number[5:8],
                                       self.number[8:12],
                                       self.number[12:])


class StateTaxNumber(AbstractTaxNumber):
    def _validate(self, raw_number: str):
        return self._sanitize(raw_number)

    def display(self) -> str:
        return self.number


class Service:
    _services = {}

    # noinspection PyShadowingBuiltins
    def __init__(self,
                 code: Union[int, str],
                 id: int,
                 description: str,
                 category: str,
                 display_name: Optional[str] = "",
                 symbol: Optional[str] = None,
                 max_weight: Optional[int] = None,
                 default_extra_services: Optional[Sequence[Union["ExtraService", int]]] = None):
        self.id = id
        self.code = to_integer(code)
        self.description = description.strip()
        self.display_name = display_name or self.description
        self.category = category.strip()
        self.symbol = symbol or "economic"
        self._symbol_image = None
        self.max_weight = max_weight

        if default_extra_services is None:
            default_extra_services = []
        self.default_extra_services = [ExtraService.get(es) for es in default_extra_services]

    def __str__(self):
        return str(self.code)

    def get_symbol_filename(self, extension='gif'):
        filename = "{}.{}".format(self.symbol, extension)
        return os.path.join(DATADIR, filename)

    @property
    def symbol_image(self) -> Image.Image:
        if not self._symbol_image:
            self._symbol_image = Image.open(self.get_symbol_filename())
        return self._symbol_image

    @classmethod
    def get(cls, number: Union['Service', int]) -> 'Service':
        if isinstance(number, Service):
            return number

        if number not in cls._services:
            cls._services[number] = cls(code=number, **SERVICES[number])
        return cls._services[number]


class ExtraService:
    _extra_services = {}

    def __init__(self, number: int, code: str, name: str):
        if not number:
            raise InvalidExtraServiceError("Invalid Extra Service Number {!r}".format(number))
        self.number = number

        if not code or len(code) != EXTRA_SERVICE_CODE_SIZE:
            raise InvalidExtraServiceError("Invalid Extra Service Code {!r}".format(code))
        self.code = code.upper()

        if not name:
            raise InvalidExtraServiceError("Invalid Extra Service Name {!r}".format(name))
        self.name = name

    def __repr__(self):
        return "<ExtraService number={!r}, code={!r}>".format(self.number, self.code)

    @classmethod
    def get(cls, number: Union['ExtraService', int]) -> 'ExtraService':
        if isinstance(number, ExtraService):
            return number

        if number not in cls._extra_services:
            cls._extra_services[number] = cls(number=number, **EXTRA_SERVICES[number])
        return cls._extra_services[number]


class User:
    def __init__(self,
                 name: str,
                 federal_tax_number: Union[str, FederalTaxNumber],
                 state_tax_number: Optional[Union[str, StateTaxNumber]] = None,
                 status_number: Optional[Union[int, str]] = None):
        self.name = name.strip()
        self.federal_tax_number = _to_federal_tax_number(federal_tax_number)

        if status_number is not None:
            status_number = to_integer(status_number)
        self.status_number = status_number

        if state_tax_number is not None:
            state_tax_number = _to_state_tax_number(state_tax_number)
        self.state_tax_number = state_tax_number

        self.contracts = []

    def add_contract(self, contract: 'Contract'):
        if contract in self.contracts:
            raise InvalidUserContractError("Contract {!r} already added".format(contract))
        self.contracts.append(contract)


class Contract:
    def __init__(self,
                 user: User,
                 number: Union[int, str],
                 regional_direction: Union[str, int, 'RegionalDirection']):

        self.user = user
        user.add_contract(self)

        self.number = to_integer(number)

        if isinstance(regional_direction, str):
            regional_direction = int(regional_direction)

        if isinstance(regional_direction, int):
            regional_direction = RegionalDirection.get(regional_direction)

        self.regional_direction = regional_direction

        self._customer_code = None
        self._start_date = None
        self._end_date = None
        self.status_code = None
        self.posting_cards = []

    @property
    def customer_code(self):
        return self._customer_code

    @customer_code.setter
    def customer_code(self, code):
        self._customer_code = to_integer(code)

    @property
    def start_date(self):
        return self._start_date

    @start_date.setter
    def start_date(self, date):
        self._start_date = to_datetime(date)

    @property
    def end_date(self):
        return self._end_date

    @end_date.setter
    def end_date(self, date):
        self._end_date = to_datetime(date)

    def add_posting_card(self, posting_card: 'PostingCard'):
        posting_card.contract = self
        self.posting_cards.append(posting_card)

    @property
    def regional_direction_number(self):
        return self.regional_direction.number

    @property
    def customer_name(self) -> str:
        return self.user.name

    def __str__(self):
        return str(self.number)

    def __repr__(self):
        return "<Contract number={!r}>".format(self.number)


class PostingCard:
    ACTIVE = True
    CANCELLED = False

    def __init__(self,
                 contract: Contract,
                 number: Union[int, str],  # 10 digits
                 administrative_code: Union[int, str]):  # 8 digits
        self.contract = contract
        self._number = to_integer(number)
        self._administrative_code = to_integer(administrative_code)
        self._start_date = None
        self._end_date = None
        self._status = None
        self._unit = None
        self.status_code = None
        self.services = []

        if self not in self.contract.posting_cards:
            self.contract.add_posting_card(self)

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, number):
        self._status = to_integer(number)

    @property
    def unit(self):
        return self._unit

    @unit.setter
    def unit(self, number):
        self._unit = to_integer(number)

    @property
    def number(self):
        return "{:010}".format(self._number)

    @property
    def administrative_code(self):
        return "{:08}".format(self._administrative_code)

    @property
    def start_date(self):
        return self._start_date

    @start_date.setter
    def start_date(self, date):
        self._start_date = to_datetime(date)

    @property
    def end_date(self):
        return self._end_date

    @end_date.setter
    def end_date(self, date):
        self._end_date = to_datetime(date)

    def add_service(self, service: Service):
        self.services.append(service)

    def get_contract_number(self):
        return self.contract.number

    def __repr__(self):
        return "<PostingCard number={!r}, contract={!r}>".format(self.number, self.get_contract_number())

    def __str__(self):
        return self.number


class RegionalDirection:
    def __init__(self, number: int, code: str, name: str):
        if not number:
            raise InvalidRegionalDirectionError("Invalid regional direction number {!r}".format(number))

        if not code:
            raise InvalidRegionalDirectionError("Invalid regional direction code {!r}".format(code))

        if not name:
            raise InvalidRegionalDirectionError("Invalid regional direction name {!r}".format(name))

        self.number = to_integer(number)
        self.code = code.upper()
        self.name = name

    @classmethod
    def get(cls, number: Union['RegionalDirection', int]) -> 'RegionalDirection':
        if isinstance(number, RegionalDirection):
            return number

        return cls(number=number, **REGIONAL_DIRECTIONS[number])

    def __repr__(self):
        return "<RegionalDirection number={!r}, code={!r}>".format(self.number, self.code)
