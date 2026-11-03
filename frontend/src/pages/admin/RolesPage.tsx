import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus } from "lucide-react";
import { useMemo, useState } from "react";

import { api } from "@/api/client";
import type { Paginated, Permission, Role } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Card, PageHeader, QueryStatus, Spinner, TenantScopeNotice } from "@/components/ui";

export function AdminRolesPage() {
  const qc = useQueryClient();
  const { user, activeTenant } = useAuth();
  const needsTenant = Boolean(user?.is_group_level && !activeTenant);

  const [newRole, setNewRole] = useState("");
  const [selected, setSelected] = useState<Role | null>(null);
  const [draftPerms, setDraftPerms] = useState<number[]>([]);
  const [filter, setFilter] = useState("");

  const roles = useQuery({
    queryKey: ["admin-roles", activeTenant, user?.tenant],
    queryFn: async () => (await api.get<Paginated<Role>>("/roles/")).data,
    enabled: !needsTenant,
  });
  const perms = useQuery({
    queryKey: ["permissions"],
    queryFn: async () => (await api.get<Permission[]>("/permissions/")).data,
  });

  const grouped = useMemo(() => {
    const map = new Map<string, Permission[]>();
    (perms.data ?? [])
      .filter(
        (p) =>
          !filter ||
          p.label.toLowerCase().includes(filter.toLowerCase()) ||
          p.name.toLowerCase().includes(filter.toLowerCase()),
      )
      .forEach((p) => {
        const arr = map.get(p.app_label) ?? [];
        arr.push(p);
        map.set(p.app_label, arr);
      });
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [perms.data, filter]);

  const createRole = useMutation({
    mutationFn: async (name: string) =>
      (await api.post("/roles/", { name })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] });
      setNewRole("");
    },
  });

  const savePerms = useMutation({
    mutationFn: async ({ id, permissions }: { id: number; permissions: number[] }) =>
      (await api.patch(`/roles/${id}/`, { permissions })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-roles"] });
      setSelected(null);
    },
  });

  function openRole(role: Role) {
    setSelected(role);
    setDraftPerms(role.permissions);
  }

  function toggle(id: number) {
    setDraftPerms((d) =>
      d.includes(id) ? d.filter((x) => x !== id) : [...d, id],
    );
  }

  if (needsTenant) {
    return (
    <div className="page-shell">
        <PageHeader
          icon={KeyRound}
          title="Rôles & droits"
          subtitle="Définition des rôles par filiale"
        />
        <TenantScopeNotice />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        icon={KeyRound}
        title="Rôles & droits"
        subtitle="Rôles et permissions de la filiale active"
      />

      <form
        className="inline-form row"
        onSubmit={(e) => {
          e.preventDefault();
          if (newRole.trim()) createRole.mutate(newRole.trim());
        }}
      >
        <input
          placeholder="Nom du nouveau rôle (ex. Directeur des risques)"
          value={newRole}
          onChange={(e) => setNewRole(e.target.value)}
        />
        <button className="btn btn-primary" disabled={createRole.isPending}>
          <Plus />
          Créer le rôle
        </button>
      </form>

      <div className="detail-grid stacked">
        <Card title="Rôles de la filiale">
          <QueryStatus
            isLoading={roles.isLoading}
            isError={roles.isError}
            isEmpty={!roles.data?.results.length}
            emptyMessage="Aucun rôle pour cette filiale."
            onRetry={() => roles.refetch()}
          >
            <table className="table">
              <thead>
                <tr>
                  <th>Rôle</th>
                  <th className="num">Droits</th>
                  <th className="num">Utilisateurs</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(roles.data?.results ?? []).map((r) => (
                  <tr
                    key={r.id}
                    className="row-clickable"
                    onClick={() => openRole(r)}
                  >
                    <td>{r.name}</td>
                    <td className="num">{r.permissions.length}</td>
                    <td className="num">{r.user_count}</td>
                    <td>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          openRole(r);
                        }}
                      >
                        Droits
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </QueryStatus>
        </Card>

        <Card
          title={
            selected ? `Droits — ${selected.name}` : "Sélectionnez un rôle"
          }
        >
          {!selected ? (
            <p className="muted">
              Choisissez un rôle pour gérer ses permissions.
            </p>
          ) : perms.isLoading ? (
            <Spinner />
          ) : (
            <>
              <input
                className="perm-filter"
                placeholder="Filtrer les permissions…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              />
              <div className="perm-scroll">
                {grouped.map(([app, list]) => (
                  <div key={app} className="perm-group">
                    <div className="perm-group-title">{app}</div>
                    {list.map((p) => (
                      <label key={p.id} className="checkbox">
                        <input
                          type="checkbox"
                          checked={draftPerms.includes(p.id)}
                          onChange={() => toggle(p.id)}
                        />
                        <span>{p.name}</span>
                      </label>
                    ))}
                  </div>
                ))}
              </div>
              <div className="row-actions" style={{ marginTop: 12 }}>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() =>
                    savePerms.mutate({
                      id: selected.id,
                      permissions: draftPerms,
                    })
                  }
                  disabled={savePerms.isPending}
                >
                  Enregistrer ({draftPerms.length})
                </button>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setSelected(null)}
                >
                  Fermer
                </button>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
