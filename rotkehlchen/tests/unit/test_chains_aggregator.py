from contextlib import ExitStack
from typing import TYPE_CHECKING

import pytest

from rotkehlchen.assets.asset import Asset
from rotkehlchen.assets.utils import get_or_create_evm_token
from rotkehlchen.chain.accounts import BlockchainAccountData
from rotkehlchen.chain.aggregator import ChainsAggregator, _module_name_to_class
from rotkehlchen.chain.evm.types import NodeName, WeightedNode, string_to_evm_address
from rotkehlchen.constants import ONE
from rotkehlchen.tests.utils.blockchain import setup_evm_addresses_activity_mock
from rotkehlchen.tests.utils.factories import make_evm_address
from rotkehlchen.tests.utils.polygon_pos import ALCHEMY_RPC_ENDPOINT
from rotkehlchen.types import AVAILABLE_MODULES_MAP, SPAM_PROTOCOL, ChainID, SupportedBlockchain

if TYPE_CHECKING:
    from rotkehlchen.chain.polygon_pos.manager import PolygonPOSManager


ALCHEMY_POLYGON_NODE = WeightedNode(
    node_info=NodeName(
        name='alchemy',
        endpoint=ALCHEMY_RPC_ENDPOINT,
        owned=False,
        blockchain=SupportedBlockchain.POLYGON_POS,
    ),
    active=True,
    weight=ONE,
)


@pytest.mark.parametrize('ethereum_modules', [[]])
def test_module_activation(blockchain):
    for module_name in AVAILABLE_MODULES_MAP:
        expected_module_type = _module_name_to_class(module_name)
        module = blockchain.activate_module(module_name)
        assert isinstance(module, expected_module_type)
        assert blockchain.eth_modules[module_name] == module


@pytest.mark.parametrize('ethereum_modules', [AVAILABLE_MODULES_MAP.keys()])
def test_module_deactivation(blockchain):
    for module_name in AVAILABLE_MODULES_MAP:
        expected_module_type = _module_name_to_class(module_name)
        assert isinstance(blockchain.eth_modules[module_name], expected_module_type)
        blockchain.deactivate_module(module_name)
        assert module_name not in blockchain.eth_modules


@pytest.mark.parametrize('ethereum_accounts', [[]])
def test_detect_evm_accounts(blockchain: 'ChainsAggregator') -> None:
    """
    Tests that the detection of EVM accounts activity in chains where they are not tracked yet
    works as expected.
    """
    # Is a contract in ethereum mainnet and should not be added anywhere else despite it having
    # activity in other chains
    eth_addy_contract = make_evm_address()

    # Is an EOA in optimism. Has activity in all chains. Should be added to optimism, and avax
    addy_eoa_1 = make_evm_address()

    # Is an EOA in ethereum mainnet. Has activity only in ethereum and in optimism. Should be
    # added to optimism and should not be added to avax
    addy_eoa_2 = make_evm_address()
    # polygon and mainnet address
    addy_eoa_3 = make_evm_address()

    # Is an EOA that is initially already added everywhere. Has activity in all chains.
    # Since is already added, should not be added again.
    everywhere_addy = make_evm_address()

    initial_accounts_data = []
    addies_to_start_with = [
        (SupportedBlockchain.ETHEREUM, eth_addy_contract),
        (SupportedBlockchain.OPTIMISM, addy_eoa_1),
        (SupportedBlockchain.ETHEREUM, addy_eoa_2),
        (SupportedBlockchain.ETHEREUM, addy_eoa_3),
        (SupportedBlockchain.ETHEREUM, everywhere_addy),
        (SupportedBlockchain.OPTIMISM, everywhere_addy),
        (SupportedBlockchain.AVALANCHE, everywhere_addy),
        (SupportedBlockchain.POLYGON_POS, everywhere_addy),
        (SupportedBlockchain.ARBITRUM_ONE, everywhere_addy),
    ]

    for chain, addy in addies_to_start_with:
        blockchain.modify_blockchain_accounts(
            blockchain=chain,
            accounts=[addy],
            append_or_remove='append',
        )
        initial_accounts_data.append(BlockchainAccountData(
            chain=chain,
            address=addy,
        ))

    with blockchain.database.user_write() as write_cursor:
        blockchain.database.add_blockchain_accounts(
            write_cursor=write_cursor,
            account_data=initial_accounts_data,
        )

    with ExitStack() as stack:
        setup_evm_addresses_activity_mock(
            stack=stack,
            chains_aggregator=blockchain,
            eth_contract_addresses=[eth_addy_contract, everywhere_addy],
            ethereum_addresses=[eth_addy_contract, everywhere_addy, addy_eoa_1, addy_eoa_2],
            optimism_addresses=[eth_addy_contract, everywhere_addy, addy_eoa_1, addy_eoa_2],
            avalanche_addresses=[eth_addy_contract, everywhere_addy, addy_eoa_1],
            polygon_pos_addresses=[everywhere_addy, addy_eoa_3],
            arbitrum_one_addresses=[everywhere_addy, addy_eoa_3],
        )

        blockchain.detect_evm_accounts()

    assert set(blockchain.accounts.eth) == {addy_eoa_1, addy_eoa_2, addy_eoa_3, eth_addy_contract, everywhere_addy}  # noqa: E501
    assert set(blockchain.accounts.optimism) == {addy_eoa_1, addy_eoa_2, everywhere_addy}
    assert set(blockchain.accounts.avax) == {addy_eoa_1, everywhere_addy}
    assert set(blockchain.accounts.polygon_pos) == {addy_eoa_3, everywhere_addy}
    assert set(blockchain.accounts.arbitrum_one) == {addy_eoa_3, everywhere_addy}

    # Also check the db
    expected_accounts_data = initial_accounts_data + [
        BlockchainAccountData(
            chain=SupportedBlockchain.ETHEREUM,
            address=addy_eoa_1,
        ),
        BlockchainAccountData(
            chain=SupportedBlockchain.AVALANCHE,
            address=addy_eoa_1,
        ),
        BlockchainAccountData(
            chain=SupportedBlockchain.OPTIMISM,
            address=addy_eoa_2,
        ),
        BlockchainAccountData(
            chain=SupportedBlockchain.POLYGON_POS,
            address=addy_eoa_3,
        ),
        BlockchainAccountData(
            chain=SupportedBlockchain.ARBITRUM_ONE,
            address=addy_eoa_3,
        ),
    ]
    accounts_in_db = []
    with blockchain.database.conn.read_ctx() as cursor:
        raw_accounts = blockchain.database.get_blockchain_accounts(cursor)
        accounts_in_db.extend([BlockchainAccountData(
            chain=SupportedBlockchain.ETHEREUM,
            address=account,
        ) for account in raw_accounts.eth])
        accounts_in_db.extend([BlockchainAccountData(
            chain=SupportedBlockchain.OPTIMISM,
            address=account,
        ) for account in raw_accounts.optimism])
        accounts_in_db.extend([BlockchainAccountData(
            chain=SupportedBlockchain.AVALANCHE,
            address=account,
        ) for account in raw_accounts.avax])
        accounts_in_db.extend([BlockchainAccountData(
            chain=SupportedBlockchain.POLYGON_POS,
            address=account,
        ) for account in raw_accounts.polygon_pos])
        accounts_in_db.extend([BlockchainAccountData(
            chain=SupportedBlockchain.ARBITRUM_ONE,
            address=account,
        ) for account in raw_accounts.arbitrum_one])

    assert set(accounts_in_db) == set(expected_accounts_data)
    assert len(accounts_in_db) == len(expected_accounts_data)


@pytest.mark.vcr(filter_query_parameters=['apikey'])
@pytest.mark.freeze_time('2023-06-19 05:16:10 GMT')
@pytest.mark.parametrize('polygon_pos_manager_connect_at_start', [(ALCHEMY_POLYGON_NODE,)])
@pytest.mark.parametrize('polygon_pos_accounts', [[make_evm_address()]])  # to connect to nodes
def test_detect_evm_accounts_spam_tx(polygon_pos_manager: 'PolygonPOSManager') -> None:
    """
    Test that an account with only erc20 transfers of spam tokens gets marked as spam
    and does not get detected as a tracked account in the EVM chain.

    The tested address has received the following spam tokens
    eip155:137/erc20:0x91bD4023A21bc12814905f251eb348e298DBC0F0
    eip155:137/erc20:0xD6198855979714255d711A4bB8BF1763d28A473B
    eip155:137/erc20:0xb76c90B51338016011Eaf27C348E3D84A623C5BF
    eip155:137/erc20:0x5522962DCE6BE2a009D29E5699a67C38b392beb9
    eip155:137/erc20:0xd9503c336512120Aa6834Ab5d9258a32940bB2C6
    eip155:137/erc20:0x9715A23D25399EF10D819e4999689de3d14eB7e2
    eip155:137/erc20:0xb266edC3706fC2A48ECFef7DD8831435f12D9966
    eip155:137/erc20:0x06732174B52743C374445E88C9b01031Bd0FB28f
    eip155:137/erc20:0xE2Ee00F49464d6B60771dc118A1bb4eb362bd154
    eip155:137/erc20:0x37CC5F5610d91325c8A8C0eD74d26A01F19e7B51

    first we check that it is marked as NOT spammed by:
    - ignoring the first asset
    - adding the second as spam asset
    - third is unknown so the address is marked as not spammed

    to verify that the address has been spammed all the remaining assets are ignored
    """
    evm_address = string_to_evm_address('0xc1C736F2Ac0e0019A188982c7c8C063976A4d8d9')
    db = polygon_pos_manager.node_inquirer.database
    with db.user_write() as write_cursor:
        db.add_to_ignored_assets(
            write_cursor=write_cursor,
            asset=Asset('eip155:137/erc20:0x91bD4023A21bc12814905f251eb348e298DBC0F0'),
        )
    get_or_create_evm_token(
        userdb=polygon_pos_manager.node_inquirer.database,
        evm_address=string_to_evm_address('0xD6198855979714255d711A4bB8BF1763d28A473B'),
        chain_id=ChainID.POLYGON_POS,
        protocol=SPAM_PROTOCOL,
    )
    assert polygon_pos_manager.transactions.address_has_been_spammed(evm_address) is False

    spam_assets = [
        Asset('eip155:137/erc20:0xb76c90B51338016011Eaf27C348E3D84A623C5BF'),
        Asset('eip155:137/erc20:0x5522962DCE6BE2a009D29E5699a67C38b392beb9'),
        Asset('eip155:137/erc20:0xd9503c336512120Aa6834Ab5d9258a32940bB2C6'),
        Asset('eip155:137/erc20:0x9715A23D25399EF10D819e4999689de3d14eB7e2'),
        Asset('eip155:137/erc20:0xb266edC3706fC2A48ECFef7DD8831435f12D9966'),
        Asset('eip155:137/erc20:0x06732174B52743C374445E88C9b01031Bd0FB28f'),
        Asset('eip155:137/erc20:0xE2Ee00F49464d6B60771dc118A1bb4eb362bd154'),
        Asset('eip155:137/erc20:0x37CC5F5610d91325c8A8C0eD74d26A01F19e7B51'),
    ]
    with db.user_write() as write_cursor:
        for asset in spam_assets:
            db.add_to_ignored_assets(write_cursor=write_cursor, asset=asset)

    assert polygon_pos_manager.transactions.address_has_been_spammed(evm_address) is True
