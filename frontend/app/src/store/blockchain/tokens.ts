import { type MaybeRef } from '@vueuse/core';
import { Blockchain } from '@rotki/common/lib/blockchain';
import isEqual from 'lodash/isEqual';
import { type ComputedRef, type Ref } from 'vue';
import { type TaskMeta } from '@/types/task';
import { TaskType } from '@/types/task-type';
import { type TokenChains, isTokenChain } from '@/types/blockchain/chains';
import {
  type EthDetectedTokensInfo,
  type EvmTokensRecord
} from '@/types/balances';

const noTokens = (): EthDetectedTokensInfo => ({
  tokens: [],
  total: 0,
  timestamp: null
});

export const useBlockchainTokensStore = defineStore('blockchain/tokens', () => {
  const ethTokens: Ref<EvmTokensRecord> = ref({});
  const optimismTokens: Ref<EvmTokensRecord> = ref({});
  const shouldRefreshBalances: Ref<boolean> = ref(true);

  const { isAssetIgnored } = useIgnoredAssetsStore();
  const { tc } = useI18n();
  const { ethAddresses } = storeToRefs(useEthAccountsStore());
  const { optimismAddresses } = storeToRefs(useChainsAccountsStore());
  const {
    fetchDetectedTokensTask,
    fetchDetectedTokens: fetchDetectedTokensCaller
  } = useBlockchainBalancesApi();

  const fetchDetected = async (
    chain: TokenChains,
    addresses: string[]
  ): Promise<void> => {
    await Promise.allSettled(
      addresses.map(address => fetchDetectedTokens(chain, address))
    );
  };

  const fetchDetectedTokens = async (
    chain: TokenChains,
    address: string | null = null
  ) => {
    try {
      if (address) {
        const { awaitTask } = useTaskStore();
        const taskType = TaskType.FETCH_DETECTED_TOKENS;

        const { taskId } = await fetchDetectedTokensTask(chain, [address]);

        const taskMeta = {
          title: tc('actions.balances.detect_tokens.task.title'),
          description: tc(
            'actions.balances.detect_tokens.task.description',
            0,
            {
              address,
              chain
            }
          ),
          address,
          chain
        };

        await awaitTask<EvmTokensRecord, TaskMeta>(
          taskId,
          taskType,
          taskMeta,
          true
        );

        await fetchDetectedTokens(chain);
      } else {
        const tokens = await fetchDetectedTokensCaller(chain, null);
        if (chain === Blockchain.ETH) {
          set(ethTokens, tokens);
        } else {
          set(optimismTokens, tokens);
        }
      }
    } catch (e) {
      logger.error(e);
    }
  };

  const getEthDetectedTokensInfo = (
    chain: MaybeRef<Blockchain>,
    address: MaybeRef<string | null>
  ): ComputedRef<EthDetectedTokensInfo> =>
    computed(() => {
      const blockchain = get(chain);
      if (!isTokenChain(blockchain)) {
        return noTokens();
      }
      const sourceTokens =
        blockchain === Blockchain.OPTIMISM ? optimismTokens : ethTokens;
      const detected = get(sourceTokens);
      const addr = get(address);
      const info = (addr && detected?.[addr]) || null;
      if (!info) {
        return noTokens();
      }

      const tokens = info.tokens
        ? info.tokens.filter(item => !get(isAssetIgnored(item)))
        : [];
      return {
        tokens,
        total: tokens.length,
        timestamp: info.lastUpdateTimestamp || null
      };
    });

  watch(ethAddresses, async (curr, prev) => {
    if (curr.length === 0 || isEqual(curr, prev)) {
      return;
    }
    await fetchDetectedTokens(Blockchain.ETH);
  });

  watch(optimismAddresses, async (curr, prev) => {
    if (curr.length === 0 || isEqual(curr, prev)) {
      return;
    }
    await fetchDetectedTokens(Blockchain.OPTIMISM);
  });

  const { isTaskRunning } = useTaskStore();
  const isEthDetecting = isTaskRunning(TaskType.FETCH_DETECTED_TOKENS, {
    chain: Blockchain.ETH
  });
  const isOptimismDetecting = isTaskRunning(TaskType.FETCH_DETECTED_TOKENS, {
    chain: Blockchain.OPTIMISM
  });

  const { fetchBlockchainBalances } = useBlockchainBalances();

  watch(isEthDetecting, async (isDetecting, wasDetecting) => {
    if (get(shouldRefreshBalances) && wasDetecting && !isDetecting) {
      await fetchBlockchainBalances({
        blockchain: Blockchain.ETH,
        ignoreCache: true
      });
    }
  });

  watch(isOptimismDetecting, async (isDetecting, wasDetecting) => {
    if (get(shouldRefreshBalances) && wasDetecting && !isDetecting) {
      await fetchBlockchainBalances({
        blockchain: Blockchain.OPTIMISM,
        ignoreCache: true
      });
    }
  });

  return {
    shouldRefreshBalances,
    fetchDetected,
    fetchDetectedTokens,
    getEthDetectedTokensInfo
  };
});

if (import.meta.hot) {
  import.meta.hot.accept(
    acceptHMRUpdate(useBlockchainTokensStore, import.meta.hot)
  );
}
