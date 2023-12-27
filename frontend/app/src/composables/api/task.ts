import { type ActionResult } from '@rotki/common/lib/data';
import { type AxiosRequestConfig } from 'axios';
import { isEmpty } from 'lodash-es';
import {
  TaskNotFoundError,
  type TaskResultResponse,
  type TaskStatus
} from '@/types/task';
import { handleResponse, validTaskStatus } from '@/services/utils';
import {
  IncompleteUpgradeError,
  SyncConflictError,
  SyncConflictPayload
} from '@/types/login';
import { api } from '@/services/rotkehlchen-api';
import { ApiValidationError } from '@/types/api/errors';

export const useTaskApi = () => {
  const queryTasks = async (): Promise<TaskStatus> => {
    const response = await api.instance.get<ActionResult<TaskStatus>>(
      `/tasks`,
      {
        validateStatus: validTaskStatus
      }
    );

    return handleResponse(response);
  };

  const queryTaskResult = async <T>(id: number): Promise<ActionResult<T>> => {
    const config: Partial<AxiosRequestConfig> = {
      validateStatus: validTaskStatus
    };

    const response = await api.instance.get<
      ActionResult<TaskResultResponse<ActionResult<T>>>
    >(`/tasks/${id}`, config);

    if (response.status === 404) {
      throw new TaskNotFoundError(`Task with id ${id} not found`);
    }

    const { outcome, statusCode } = handleResponse(response);

    if (outcome) {
      const { result, message } = outcome;

      if (statusCode === 300) {
        if (typeof result === 'object') {
          if (isEmpty(result)) {
            throw new IncompleteUpgradeError(message);
          }
          throw new SyncConflictError(
            message,
            SyncConflictPayload.parse(result)
          );
        }
      } else if (statusCode === 400) {
        throw new ApiValidationError(message);
      }
      return outcome;
    }

    throw new Error('No result');
  };

  const cancelAsyncTask = async (id: number): Promise<boolean> => {
    const config: Partial<AxiosRequestConfig> = {
      validateStatus: validTaskStatus
    };

    const response = await api.instance.delete<ActionResult<boolean>>(
      `/tasks/${id}`,
      config
    );

    if (response.status === 404) {
      throw new TaskNotFoundError(`Task with id ${id} not found`);
    }

    return handleResponse(response);
  };

  return {
    queryTasks,
    queryTaskResult,
    cancelAsyncTask
  };
};
