# OmagMES UI reference: FittingMES

**Purpose:** Record the existing FittingMES presentation and interaction patterns before adapting the OmagMES React interface. FittingMES is a UI reference only; its process assumptions, data model, routes, machine logic, and SQL schema are not OmagMES requirements.

## Source files inspected

| FittingMES source | UI patterns used as reference |
| --- | --- |
| `D:/AI/FittingMES/app/templates/navigation.html` | Compact horizontal top-level tabs; expandable Production, Depallet, and Setting groups; a second row of compact page tabs; selected-route highlighting; preserve route/context selections while moving among related pages. |
| `D:/AI/FittingMES/app/templates/api_base.html` | Shared page title/header, navigation shell, compact white panels on a light gray-blue page, small controls, thin borders, blue primary/selected states, scrollable tables, visible focus ring, and restrained status/error colors. No sidebar. |
| `D:/AI/FittingMES/app/templates/production.html` | Production setup/context above a dense editable lot table; selected row; cell-level quantity/text editing; explicit per-row SAVE and inline status; secondary detail sections remain tied to the selected lot. |
| `D:/AI/FittingMES/app/templates/reject.html` | Context-first entry form, visible product/lot selection, compact quantity/reason controls, explicit SAVE/CANCEL/DELETE actions, saved-entry table, and inline success/error messages. |
| `D:/AI/FittingMES/app/templates/logger.html` and `D:/AI/FittingMES/app/templates/logger_summary.html` | Compact time-event form and adjacent/history table; explicit save and edit/cancel flow; separate event capture from time summary. Only the generic form/history presentation is reused. |
| `D:/AI/FittingMES/app/templates/mould.html` | Filter toolbar, master list with selected row, adjacent detail/actions, separate histories, colored status text, and confirmation before lifecycle transitions. |
| `D:/AI/FittingMES/app/templates/press_mc.html` | Master-data list/detail, inline configuration controls, capability/status summary and history. OmagMES will not copy Press configuration or capability rules. |
| `D:/AI/FittingMES/app/templates/logger_master.html` | Read-only master review with counts, warnings, and compact reference tables. Suitable for clearly unapproved OmagMES demo-master visibility, not master approval or production maintenance. |

## Patterns to carry into React

- Use a compact horizontal, three-group navigation that mirrors FittingMES: **Production**, **Depallet**, **Setting**. Group expansion reveals a same-row-height subnavigation with the active page highlighted in blue. There is no permanent sidebar.
- Keep a compact page heading/context strip above the navigation and page content. Replace the decorative dashboard-style shell with the FittingMES light gray-blue canvas, white bordered panels, compact controls, thin table rules, and blue active/primary actions.
- Keep related workflow context visible at the point of entry. The selected OmagMES Lot ID and its Product/Color/Run context persist when navigating to Wet Reject, Wet Run Log, Curing, and Depallet; selection remains keyed by immutable Lot ID.
- Keep editable quantities adjacent to their labels, with explicit SAVE. AutoCal/Recal remains a suggestion action that fills editable fields but never saves; confirmation/validation and save outcomes use visible inline status/alert messages.
- Present saved records as compact, scrollable tables or histories, and keep selected-row/detail patterns for Mould. Lifecycle transitions require a reason and a confirmation step.
- Render demo master/standard/reject-reason information as review-only tables and warnings. Do not introduce production master-data writes, unapproved standard values, or authentication claims.

## OmagMES navigation mapping

| FittingMES group | OmagMES submenu pages |
| --- | --- |
| Production | Production, Wet Run Log, Wet Reject, Wet OEE, Curing |
| Depallet | Depallet |
| Setting | Mould, Settings |

Curing is grouped with Production as the closest OmagMES analogue to FittingMES's production-related Usage page; this is only menu placement, not a transfer of its business logic. Wet Reject remains under Production because it is specifically for the Wet line; no Depallet reject workflow was invented. Mould belongs under Setting, like the existing FittingMES Mould management page. Every requested OmagMES module remains reachable, and no FittingMES page or route is copied.

## Deliberate differences

- Keep React + TypeScript + Vite and FastAPI REST; do not port Jinja templates, inline template scripts, or FittingMES server routes.
- OmagMES is one coupled Press + Wet Line, not FittingMES's production-plan/press/shift/machine hierarchy. Wet Run Log categories are OmagMES's manually confirmed classifications; do not reuse LOGGER taxonomy or machine selection.
- Production is Run/Lot-centric. Product change starts a new Run and Lot; Color change starts a new Lot in the existing Run. Lot ID remains immutable; LotName is editable and may be duplicated.
- AutoCal and wet-reject suggestions are mock suggestions; `ProductCnt` means Drops, `CYC` is excluded, camera Wet counts mean Pieces, and Wet Reject uses dynamic `cntR*` counters, not `R*` button states.
- OEE remains explicitly simulated; Dry Line/Depallet is excluded. No unapproved standards or master values are loaded.
- A custom accessible React confirmation dialog may be used for destructive or lifecycle actions; FittingMES primarily uses native `confirm()`. This is a deliberate accessible React adaptation, not a workflow change.

## Existing OmagMES baseline reviewed before adaptation

The React shell, shared page switching, workflow forms and mock-only API integration are in `frontend/src/App.tsx`; shared responsive styles are in `frontend/src/styles.css`. Confirmed OmagMES rules are recorded in `docs/OmagMES_Confirmed_Business_Rules.md`. The implementation change should be limited to presentation, navigation grouping, and context retention; do not modify backend behavior, FittingMES, legacy SQL, or database scripts.
