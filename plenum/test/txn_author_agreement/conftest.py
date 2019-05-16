import pytest
from copy import deepcopy

from state.pruning_state import PruningState
from storage.kv_in_memory import KeyValueStorageInMemory
from ledger.compact_merkle_tree import CompactMerkleTree

from plenum.common.constants import (
    CURRENT_PROTOCOL_VERSION, TXN_AUTHOR_AGREEMENT_AML, AML_VERSION, AML, AML_CONTEXT
)
from plenum.common.request import Request
from plenum.common.ledger import Ledger
from plenum.common.util import randomString

from plenum.server.config_req_handler import ConfigReqHandler

from plenum.test.txn_author_agreement.helper import (
    TaaData, expected_state_data, expected_data
)

from plenum.test.helper import sdk_get_and_check_replies, sdk_sign_and_submit_req_obj
from plenum.test.delayers import req_delay
from plenum.test.testing_utils import FakeSomething
from plenum.test.node_catchup.helper import ensure_all_nodes_have_same_data
from plenum.test.pool_transactions.helper import sdk_sign_and_send_prepared_request
from .helper import (
    set_txn_author_agreement as _set_txn_author_agreement,
    get_txn_author_agreement as _get_txn_author_agreement,
    calc_taa_digest, gen_random_txn_author_agreement
)


@pytest.fixture
def config_ledger(tmpdir_factory):
    tdir = tmpdir_factory.mktemp('').strpath
    return Ledger(CompactMerkleTree(),
                  dataDir=tdir)


@pytest.fixture
def config_state():
    return PruningState(KeyValueStorageInMemory())


@pytest.fixture
def config_req_handler(config_state,
                       config_ledger):
    return ConfigReqHandler(config_ledger,
                            config_state,
                            domain_state=FakeSomething(),
                            bls_store=FakeSomething())


@pytest.fixture(scope="module")
def nodeSetWithOneNodeResponding(txnPoolNodeSet):
    # the order of nodes the client sends requests to is [Alpha, Beta, Gamma, Delta]
    # delay all requests to Beta, Gamma and Delta
    # we expect that it's sufficient for the client to get Reply from Alpha only
    # as for write requests, we can send it to 1 node only, and it will be propagated to others
    for node in txnPoolNodeSet[1:]:
        node.clientIbStasher.delay(req_delay())
    return txnPoolNodeSet


@pytest.fixture
def random_taa(request):
    marker = request.node.get_marker('random_taa')
    return gen_random_txn_author_agreement(
        **({} if marker is None else marker.kwargs))


@pytest.fixture
def set_txn_author_agreement(
    looper, txnPoolNodeSet, sdk_pool_handle, sdk_wallet_trustee, random_taa
):
    def wrapped(text=None, version=None):
        text = random_taa[0] if text is None else text
        version = random_taa[1] if version is None else version
        res = _set_txn_author_agreement(looper, sdk_pool_handle, sdk_wallet_trustee, text, version)
        ensure_all_nodes_have_same_data(looper, txnPoolNodeSet)  # TODO do we need that
        return res

    return wrapped


@pytest.fixture
def get_txn_author_agreement(
    looper, txnPoolNodeSet, sdk_pool_handle, sdk_wallet_client
):
    def wrapped(digest=None, version=None, timestamp=None):
        return _get_txn_author_agreement(
            looper, sdk_pool_handle, sdk_wallet_client,
            digest=digest, version=version, timestamp=timestamp
        )

    return wrapped


@pytest.fixture
def activate_taa(set_txn_author_agreement):
    return set_txn_author_agreement()


@pytest.fixture(scope='module')
def request_kwargs(sdk_wallet_trustee):
    return dict(
        identifier=sdk_wallet_trustee[1],
        reqId=5,
        protocolVersion=CURRENT_PROTOCOL_VERSION,
        operation={
            'type': TXN_AUTHOR_AGREEMENT_AML,
            AML_VERSION: randomString(),
            AML: {'Nice way': 'very good way to accept agreement'},
            AML_CONTEXT: randomString()
        }
    )


@pytest.fixture(scope="function")
def taa_aml_request(request_kwargs):
    request_kwargs = deepcopy(request_kwargs)
    request_kwargs['operation'][AML_VERSION] = randomString()
    request_kwargs['operation'][AML_CONTEXT] = randomString()
    return Request(**request_kwargs)


@pytest.fixture(scope="module")
def taa_aml_request_module(request_kwargs):
    return Request(**request_kwargs)


# TODO serve AML routine with helpers/fixtures similar to TAA
@pytest.fixture(scope="module")
def set_txn_author_agreement_aml(
    looper, txnPoolNodeSet, taa_aml_request_module,
    sdk_pool_handle, sdk_wallet_trustee
):
    req = sdk_sign_and_submit_req_obj(
        looper, sdk_pool_handle, sdk_wallet_trustee, taa_aml_request_module
    )
    sdk_get_and_check_replies(looper, [req])[0]


@pytest.fixture
def taa_input_data():
    return [
        TaaData(*gen_random_txn_author_agreement(32, 8), n, n + 10)
        for n in range(10)
    ]


@pytest.fixture
def taa_expected_state_data(taa_input_data):
    return {data.version: expected_state_data(data) for data in taa_input_data}


@pytest.fixture
def taa_expected_data(taa_input_data):
    return {data.version: expected_data(data) for data in taa_input_data}


@pytest.fixture
def taa_expected_digests(taa_input_data):
    return {data.version: calc_taa_digest(data.text, data.version) for data in taa_input_data}
