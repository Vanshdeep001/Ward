import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, USE_MOCKS } from './client.js'

export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000 })
export const useResources = () => useQuery({ queryKey: ['resources'], queryFn: api.resources })
export const useAlerts = () => useQuery({ queryKey: ['alerts'], queryFn: api.alerts })
export const useRules = () => useQuery({ queryKey: ['rules'], queryFn: api.rules })
export const useCosts = () => useQuery({ queryKey: ['costs'], queryFn: api.costs })
export const usePredictions = () => useQuery({ queryKey: ['predictions'], queryFn: api.predictions })
export const useFindings = () => useQuery({ queryKey: ['findings'], queryFn: api.findings })
export const useConflicts = () => useQuery({ queryKey: ['conflicts'], queryFn: api.conflicts })

/* Connected AWS accounts. One query drives the whole demo-vs-live distinction: an empty list means
   Ward is running on the sample account, a `connected` row means it is reading a real one. */
export const useAccounts = () =>
  useQuery({ queryKey: ['accounts'], queryFn: api.accounts, retry: false })

export function useConnection() {
  const { data, isLoading, isError } = useAccounts()
  const accounts = data?.items ?? []
  const connected = accounts.find((a) => a.status === 'connected') ?? null
  return { accounts, connected, isDemo: !connected, isLoading, isError, usingMocks: USE_MOCKS }
}

// Whether Ward itself has AWS credentials and a principal to be trusted — checked before onboarding.
export const useSetupStatus = () =>
  useQuery({ queryKey: ['accounts', 'setup'], queryFn: api.setupStatus, retry: false, enabled: !USE_MOCKS })

export function useCreateAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.createAccount,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['accounts'] }),
  })
}

export function useConnectAccount() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, roleArn }) => api.connectAccount(id, roleArn),
    // Connecting swaps the inventory server-side, so everything derived from it is now stale.
    onSuccess: () => qc.invalidateQueries(),
  })
}

export function useDisconnectAccount() {
  const qc = useQueryClient()
  return useMutation({ mutationFn: api.disconnectAccount, onSuccess: () => qc.invalidateQueries() })
}

export function useSnooze() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, hours }) => api.snoozeAlert(id, hours),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
}

export function useActivateRule() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.activateRule,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  })
}
