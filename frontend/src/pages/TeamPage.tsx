import {
  useEffect,
  useMemo,
  useState,
} from "react";

import { useTranslation } from "react-i18next";

import {
  Check,
  Clock3,
  Mail,
  Plus,
  ShieldCheck,
  Store as StoreIcon,
  UserRound,
  Users,
  X,
} from "lucide-react";

import {
  cancelTeamInvitation,
  createTeamInvitation,
  getTeam,
  getTeamInvitations,
  updateTeamMember,
  type TeamInvitation,
  type TeamMember,
  type TeamRole,
  type TeamUsage,
} from "../services/team";

import {
  getStores,
  type Store,
} from "../services/stores";


interface TeamPageProps {
  canWrite: boolean;
}


type EditableRole =
  | "manager"
  | "operator"
  | "analyst";


interface InvitationForm {
  email: string;
  role: EditableRole;
  allStores: boolean;
  storeIds: number[];
}


const EMPTY_FORM: InvitationForm = {
  email: "",
  role: "operator",
  allStores: true,
  storeIds: [],
};


function extractError(
  error: unknown,
  fallback: string,
) {
  if (
    typeof error === "object"
    && error !== null
    && "response" in error
  ) {
    const response = (
      error as {
        response?: {
          data?: {
            detail?:
              | string
              | {
                  message?: string;
                };
          };
        };
      }
    ).response;

    const detail =
      response?.data?.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (
      detail
      && typeof detail === "object"
      && detail.message
    ) {
      return detail.message;
    }
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}


export default function TeamPage({
  canWrite,
}: TeamPageProps) {
  const { t } = useTranslation();

  const [members, setMembers] =
    useState<TeamMember[]>([]);

  const [invitations, setInvitations] =
    useState<TeamInvitation[]>([]);

  const [stores, setStores] =
    useState<Store[]>([]);

  const [usage, setUsage] =
    useState<TeamUsage>({
      used: 0,
      limit: 0,
      remaining: 0,
    });

  const [loading, setLoading] =
    useState(true);

  const [saving, setSaving] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);

  const [message, setMessage] =
    useState<string | null>(null);

  const [inviteOpen, setInviteOpen] =
    useState(false);

  const [form, setForm] =
    useState<InvitationForm>(
      EMPTY_FORM,
    );


  const load = async () => {
    setLoading(true);
    setError(null);

    try {
      const [
        teamResponse,
        invitationResponse,
        storeResponse,
      ] = await Promise.all([
        getTeam(),
        getTeamInvitations(),
        getStores(),
      ]);

      setMembers(
        teamResponse.items,
      );

      setUsage(
        teamResponse.usage,
      );

      setInvitations(
        invitationResponse.items,
      );

      setStores(
        storeResponse.items,
      );
    } catch (err) {
      setError(
        extractError(
          err,
          t("teamI18nUnexpectedError"),
        ),
      );
    } finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    void load();
  }, []);


  const activeMembers =
    useMemo(
      () =>
        members.filter(
          (member) =>
            member.active,
        ),
      [members],
    );


  const inactiveMembers =
    useMemo(
      () =>
        members.filter(
          (member) =>
            !member.active,
        ),
      [members],
    );


  const pendingInvitations =
    useMemo(
      () =>
        invitations.filter(
          (invitation) =>
            invitation.status
            === "pending",
        ),
      [invitations],
    );


  const roleLabel = (
    role: TeamRole,
  ) => {
    switch (role) {
      case "owner":
        return t("teamRoleOwner");

      case "manager":
        return t("teamRoleManager");

      case "operator":
        return t("teamRoleOperator");

      case "analyst":
        return t("teamRoleAnalyst");

      default:
        return role;
    }
  };


  const accessLabel = (
    member:
      | TeamMember
      | TeamInvitation,
  ) => {
    if (member.all_stores) {
      return t("teamAllStores");
    }

    if (!member.stores.length) {
      return t("teamNoStores");
    }

    return member.stores
      .map((store) => store.name)
      .join(", ");
  };


  const openInvitation = () => {
    setError(null);
    setMessage(null);

    setForm({
      ...EMPTY_FORM,
    });

    setInviteOpen(true);
  };


  const handleInvite =
    async () => {
      const email =
        form.email
          .trim()
          .toLowerCase();

      if (!email) {
        setError(
          t("teamEmailRequired"),
        );
        return;
      }

      if (
        !form.allStores
        && !form.storeIds.length
      ) {
        setError(
          t("teamStoreRequired"),
        );
        return;
      }

      setSaving(true);
      setError(null);
      setMessage(null);

      try {
        await createTeamInvitation({
          email,
          role: form.role,
          all_stores:
            form.allStores,
          store_ids:
            form.allStores
              ? []
              : form.storeIds,
        });

        setInviteOpen(false);

        setMessage(
          t("teamInvitationCreated"),
        );

        await load();
      } catch (err) {
        setError(
          extractError(
          err,
          t("teamI18nUnexpectedError"),
        ),
        );
      } finally {
        setSaving(false);
      }
    };


  const handleCancelInvitation =
    async (
      invitationId: number,
    ) => {
      setError(null);
      setMessage(null);

      try {
        await cancelTeamInvitation(
          invitationId,
        );

        setMessage(
          t("teamInvitationCancelled"),
        );

        await load();
      } catch (err) {
        setError(
          extractError(
          err,
          t("teamI18nUnexpectedError"),
        ),
        );
      }
    };


  const handleActiveChange =
    async (
      member: TeamMember,
      active: boolean,
    ) => {
      setError(null);
      setMessage(null);

      try {
        await updateTeamMember(
          member.id,
          {
            active,
          },
        );

        setMessage(
          active
            ? t("teamMemberReactivated")
            : t("teamMemberDeactivated"),
        );

        await load();
      } catch (err) {
        setError(
          extractError(
          err,
          t("teamI18nUnexpectedError"),
        ),
        );
      }
    };


  const renderMember = (
    member: TeamMember,
  ) => (
    <article
      key={member.id}
      className={
        `panel team-member-card ${
          member.active
            ? ""
            : "is-inactive"
        }`
      }
    >
      <div className="team-member-main">
        <div className="management-icon">
          <UserRound size={20} />
        </div>

        <div className="team-member-identity">
          <div className="team-member-name-row">
            <h3>{member.name}</h3>

            <span
              className={
                `team-status ${
                  member.active
                    ? "active"
                    : "inactive"
                }`
              }
            >
              {
                member.active
                  ? t("teamActive")
                  : t("teamInactive")
              }
            </span>
          </div>

          <span className="team-member-email">
            {member.email}
          </span>
        </div>
      </div>

      <div className="team-member-details">
        <div>
          <span>{t("teamRole")}</span>
          <strong>
            {roleLabel(member.role)}
          </strong>
        </div>

        <div>
          <span>{t("teamAccess")}</span>
          <strong>
            {accessLabel(member)}
          </strong>
        </div>
      </div>

      {
        canWrite
        && member.role !== "owner"
        && (
          <div className="team-member-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={() =>
                void handleActiveChange(
                  member,
                  !member.active,
                )
              }
            >
              {
                member.active
                  ? t("teamDeactivate")
                  : t("teamReactivate")
              }
            </button>
          </div>
        )
      }
    </article>
  );


  return (
    <div className="content">
      <section className="page-heading">
        <div>
          <span className="eyebrow">
            DIAGLOB TECH
          </span>

          <h1>{t("team")}</h1>

          <p>
            {t("teamSubtitle")}
          </p>
        </div>

        {
          canWrite
          && (
            <button
              type="button"
              className="primary-button"
              onClick={openInvitation}
            >
              <Plus size={17} />
              {t("teamInviteMember")}
            </button>
          )
        }
      </section>


      <section className="team-summary">
        <div className="panel team-summary-card">
          <Users size={21} />

          <div>
            <strong>
              {usage.used} / {usage.limit}
            </strong>

            <span>
              {t("teamActiveMembers")}
            </span>
          </div>
        </div>

        <div className="panel team-summary-card">
          <Check size={21} />

          <div>
            <strong>
              {usage.remaining}
            </strong>

            <span>
              {t("teamAvailableSlots")}
            </span>
          </div>
        </div>

        <div className="panel team-summary-card">
          <Mail size={21} />

          <div>
            <strong>
              {pendingInvitations.length}
            </strong>

            <span>
              {t("teamPendingInvitations")}
            </span>
          </div>
        </div>
      </section>


      {
        usage.remaining === 0
        && canWrite
        && (
          <div className="team-capacity-note">
            <ShieldCheck size={18} />

            <span>
              {t("teamCapacityNotice")}
            </span>
          </div>
        )
      }


      {
        error
        && (
          <div className="management-feedback error">
            {error}
          </div>
        )
      }

      {
        message
        && (
          <div className="management-feedback success">
            {message}
          </div>
        )
      }


      {
        loading
        ? (
          <div className="panel team-loading">
            {t("teamLoading")}
          </div>
        )
        : (
          <>
            <section className="team-section">
              <div className="team-section-heading">
                <div>
                  <h2>
                    {t("teamActiveSection")}
                  </h2>

                  <span>
                    {activeMembers.length}
                  </span>
                </div>
              </div>

              <div className="management-grid">
                {
                  activeMembers.map(
                    renderMember,
                  )
                }
              </div>
            </section>


            {
              inactiveMembers.length > 0
              && (
                <section className="team-section">
                  <div className="team-section-heading">
                    <div>
                      <h2>
                        {t("teamInactiveSection")}
                      </h2>

                      <span>
                        {inactiveMembers.length}
                      </span>
                    </div>
                  </div>

                  <div className="management-grid">
                    {
                      inactiveMembers.map(
                        renderMember,
                      )
                    }
                  </div>
                </section>
              )
            }


            <section className="team-section">
              <div className="team-section-heading">
                <div>
                  <h2>
                    {t("teamInvitations")}
                  </h2>

                  <span>
                    {pendingInvitations.length}
                  </span>
                </div>
              </div>

              {
                pendingInvitations.length
                ? (
                  <div className="team-invitations-list">
                    {
                      pendingInvitations.map(
                        (invitation) => (
                          <div
                            key={invitation.id}
                            className="panel team-invitation-row"
                          >
                            <div className="team-invitation-icon">
                              <Clock3 size={18} />
                            </div>

                            <div className="team-invitation-copy">
                              <strong>
                                {invitation.email}
                              </strong>

                              <span>
                                {
                                  roleLabel(
                                    invitation.role,
                                  )
                                }
                                {" · "}
                                {
                                  accessLabel(
                                    invitation,
                                  )
                                }
                              </span>
                            </div>

                            {
                              canWrite
                              && (
                                <button
                                  type="button"
                                  className="secondary-button"
                                  onClick={() =>
                                    void handleCancelInvitation(
                                      invitation.id,
                                    )
                                  }
                                >
                                  {t("teamCancelInvitation")}
                                </button>
                              )
                            }
                          </div>
                        ),
                      )
                    }
                  </div>
                )
                : (
                  <div className="panel team-empty">
                    <Mail size={23} />

                    <span>
                      {t("teamNoPendingInvitations")}
                    </span>
                  </div>
                )
              }
            </section>
          </>
        )
      }


      {
        inviteOpen
        && (
          <div className="management-modal-backdrop">
            <div className="management-modal">
              <div className="management-modal-header">
                <div>
                  <span className="eyebrow">
                    {t("team")}
                  </span>

                  <h2>
                    {t("teamInviteMember")}
                  </h2>
                </div>

                <button
                  type="button"
                  className="icon-button"
                  onClick={() =>
                    setInviteOpen(false)
                  }
                  aria-label={t("close")}
                >
                  <X size={19} />
                </button>
              </div>


              <div className="management-form team-invite-form">
                <label>
                  <span>
                    {t("teamEmail")}
                  </span>

                  <input
                    type="email"
                    value={form.email}
                    placeholder="persona@empresa.com"
                    onChange={(event) =>
                      setForm(
                        (current) => ({
                          ...current,
                          email:
                            event.target.value,
                        }),
                      )
                    }
                  />
                </label>


                <label>
                  <span>
                    {t("teamRole")}
                  </span>

                  <select
                    value={form.role}
                    onChange={(event) =>
                      setForm(
                        (current) => ({
                          ...current,
                          role:
                            event.target.value as EditableRole,
                        }),
                      )
                    }
                  >
                    <option value="operator">
                      {t("teamRoleOperator")}
                    </option>

                    <option value="manager">
                      {t("teamRoleManager")}
                    </option>

                    <option value="analyst">
                      {t("teamRoleAnalyst")}
                    </option>
                  </select>
                </label>


                <div className="team-access-box">
                  <div className="team-access-title">
                    <StoreIcon size={17} />

                    <div>
                      <strong>
                        {t("teamStoreAccess")}
                      </strong>

                      <span>
                        {t("teamStoreAccessHelp")}
                      </span>
                    </div>
                  </div>

                  <label className="team-radio">
                    <input
                      type="radio"
                      checked={form.allStores}
                      onChange={() =>
                        setForm(
                          (current) => ({
                            ...current,
                            allStores: true,
                            storeIds: [],
                          }),
                        )
                      }
                    />

                    <span>
                      {t("teamAllStores")}
                    </span>
                  </label>

                  <label className="team-radio">
                    <input
                      type="radio"
                      checked={!form.allStores}
                      onChange={() =>
                        setForm(
                          (current) => ({
                            ...current,
                            allStores: false,
                          }),
                        )
                      }
                    />

                    <span>
                      {t("teamSelectedStores")}
                    </span>
                  </label>


                  {
                    !form.allStores
                    && (
                      <div className="team-store-selection">
                        {
                          stores.map(
                            (store) => {
                              const selected =
                                form.storeIds.includes(
                                  store.id,
                                );

                              return (
                                <label
                                  key={store.id}
                                  className="team-store-option"
                                >
                                  <input
                                    type="checkbox"
                                    checked={selected}
                                    onChange={() =>
                                      setForm(
                                        (current) => ({
                                          ...current,
                                          storeIds:
                                            selected
                                              ? current.storeIds.filter(
                                                  (id) =>
                                                    id !== store.id,
                                                )
                                              : [
                                                  ...current.storeIds,
                                                  store.id,
                                                ],
                                        }),
                                      )
                                    }
                                  />

                                  <span>
                                    {store.name}
                                  </span>
                                </label>
                              );
                            },
                          )
                        }
                      </div>
                    )
                  }
                </div>


                <p className="team-invite-help">
                  {t("teamInvitationHelp")}
                </p>
              </div>


              <div className="management-modal-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() =>
                    setInviteOpen(false)
                  }
                  disabled={saving}
                >
                  {t("cancel")}
                </button>

                <button
                  type="button"
                  className="primary-button"
                  onClick={() =>
                    void handleInvite()
                  }
                  disabled={saving}
                >
                  {
                    saving
                      ? t("teamSendingInvitation")
                      : t("teamSendInvitation")
                  }
                </button>
              </div>
            </div>
          </div>
        )
      }
    </div>
  );
}
