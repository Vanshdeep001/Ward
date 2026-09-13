import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client.js'

export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 30_000 })
export const useResources = () => useQuery({ queryKey: ['resources'], queryFn: api.resources })
export const useAlerts = () => useQuery({ queryKey: ['alerts'], queryFn: api.alerts })
export const useRules = () => useQuery({ queryKey: ['rules'], queryFn: api.rules })
export const useCosts = () => useQuery({ queryKey: ['costs'], queryFn: api.costs })
export const usePredictions = () => useQuery({ queryKey: ['predictions'], queryFn: api.predictions })
export const useFindings = () => useQuery({ queryKey: ['findings'], queryFn: api.findings })
export const useConflicts = () => useQuery({ queryKey: ['conflicts'], queryFn: api.conflicts })

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
