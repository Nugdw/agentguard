// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Minimal ERC-721 view used to check Agent ID ownership.
/// @dev Agent ID on BNB Chain is SPACE ID Agent ID (symbol AI), an
///      ERC-721 that is non-transferable and limited to one per user.
interface IAgentId {
    function balanceOf(address owner) external view returns (uint256);
}

/// @title AgentGuard — Agent ID-Verified Mint Safety Registry
/// @notice On-chain safety registry for agent-targeted projects on BNB Chain.
///         Anyone may read project scores. Only verified Agent ID holders may
///         register projects and cast or change a safety vote, because every
///         state-changing entry point checks Agent ID ownership on-chain.
///         One Agent ID holder address gets exactly one vote per project and
///         may change that vote at any time; tallies are updated atomically.
///
/// @dev Owner permissions (disclosed, per hackathon safety rules):
///      - The owner may deactivate or reactivate a registered project
///        (moderation against spam or impersonation). Deactivation stops new
///        votes; existing votes and scores stay readable forever.
///      - The owner may transfer ownership to a new address.
///      - The owner has NO other powers: this contract holds no user funds,
///        exposes no withdrawal function, cannot mint anything, cannot set
///        fees or taxes, and cannot alter or delete votes or projects.
///      There is no pause function, no upgrade proxy, and no hidden mint.
contract AgentGuard {
    /// @notice Official Agent ID contract on BNB Chain (chain id 56).
    address public constant AGENT_ID_BNB =
        0x60B9262456dE011F7d15a54CdD8c48bAaa8B022F;

    IAgentId public immutable agentId;
    address public owner;

    enum Vote {
        None,
        Safe,
        Risky
    }

    struct Project {
        address projectContract; // contract being rated (address(0) = none)
        address registrant;
        string name;
        string infoURI; // project website / repo / docs link
        uint64 registeredAt;
        uint32 safeVotes;
        uint32 riskyVotes;
        bool active;
        bool exists;
    }

    Project[] private _projects;

    /// @notice One vote per Agent ID holder address per project.
    mapping(uint256 => mapping(address => Vote)) public voteOf;

    /// @notice A project contract may be registered only once.
    mapping(address => uint256) public projectIdByContract;

    /// @notice Number of distinct Agent ID holder addresses that have ever
    ///         interacted (registered or voted) — the hackathon metric.
    mapping(address => bool) public hasInteracted;
    uint256 public uniqueInteractors;

    event ProjectRegistered(
        uint256 indexed projectId,
        address indexed projectContract,
        address indexed registrant,
        string name,
        string infoURI
    );
    event Voted(
        uint256 indexed projectId,
        address indexed voter,
        Vote vote,
        string note
    );
    event VoteChanged(
        uint256 indexed projectId,
        address indexed voter,
        Vote oldVote,
        Vote newVote,
        string note
    );
    event ProjectActiveSet(uint256 indexed projectId, bool active);
    event OwnershipTransferred(
        address indexed oldOwner,
        address indexed newOwner
    );

    error NotAgentIdHolder(address caller);
    error NotOwner(address caller);
    error ProjectNotFound(uint256 projectId);
    error ProjectInactive(uint256 projectId);
    error AlreadyRegistered(address projectContract);
    error EmptyName();
    error InvalidVote();

    modifier onlyAgent() {
        if (agentId.balanceOf(msg.sender) == 0) {
            revert NotAgentIdHolder(msg.sender);
        }
        _;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner(msg.sender);
        _;
    }

    /// @param agentIdContract Agent ID ERC-721 contract. On BNB Chain
    ///        mainnet pass AGENT_ID_BNB; the parameter exists so the same
    ///        code can be tested against a mock and deployed unchanged.
    constructor(address agentIdContract) {
        require(agentIdContract != address(0), "agentId=0");
        agentId = IAgentId(agentIdContract);
        owner = msg.sender;
    }

    // ---------------------------------------------------------------
    // Core flow
    // ---------------------------------------------------------------

    /// @notice Register a project contract for community safety rating.
    /// @dev Requires an Agent ID. The same contract address can be
    ///      registered only once, so scores cannot be split or reset.
    function registerProject(
        address projectContract,
        string calldata name,
        string calldata infoURI
    ) external onlyAgent returns (uint256 projectId) {
        if (bytes(name).length == 0) revert EmptyName();
        if (
            projectContract != address(0) &&
            projectIdByContract[projectContract] != 0
        ) {
            revert AlreadyRegistered(projectContract);
        }

        projectId = _projects.length + 1; // ids start at 1; 0 = not found
        _projects.push(
            Project({
                projectContract: projectContract,
                registrant: msg.sender,
                name: name,
                infoURI: infoURI,
                registeredAt: uint64(block.timestamp),
                safeVotes: 0,
                riskyVotes: 0,
                active: true,
                exists: true
            })
        );
        if (projectContract != address(0)) {
            projectIdByContract[projectContract] = projectId;
        }
        _markInteracted(msg.sender);
        emit ProjectRegistered(
            projectId,
            projectContract,
            msg.sender,
            name,
            infoURI
        );
    }

    /// @notice Cast or change your safety vote on a project.
    /// @param vote_ Safe or Risky (None is rejected; use your one vote).
    /// @param note Optional short risk note, carried in the event log so
    ///        front-ends can show *why* a holder voted the way they did.
    function vote(
        uint256 projectId,
        Vote vote_,
        string calldata note
    ) external onlyAgent {
        Project storage p = _project(projectId);
        if (!p.active) revert ProjectInactive(projectId);
        if (vote_ == Vote.None) revert InvalidVote();

        Vote old = voteOf[projectId][msg.sender];
        if (old == vote_) {
            // Same choice again: refresh the note only, tallies unchanged.
            emit Voted(projectId, msg.sender, vote_, note);
            return;
        }
        if (old == Vote.Safe) p.safeVotes -= 1;
        if (old == Vote.Risky) p.riskyVotes -= 1;
        if (vote_ == Vote.Safe) p.safeVotes += 1;
        if (vote_ == Vote.Risky) p.riskyVotes += 1;
        voteOf[projectId][msg.sender] = vote_;

        _markInteracted(msg.sender);
        if (old == Vote.None) {
            emit Voted(projectId, msg.sender, vote_, note);
        } else {
            emit VoteChanged(projectId, msg.sender, old, vote_, note);
        }
    }

    // ---------------------------------------------------------------
    // Reads
    // ---------------------------------------------------------------

    function projectCount() external view returns (uint256) {
        return _projects.length;
    }

    function getProject(
        uint256 projectId
    ) external view returns (Project memory) {
        return _project(projectId);
    }

    /// @notice Safety score in basis points of Safe votes, plus raw tallies.
    /// @dev scoreBps = safe * 10000 / (safe + risky); 0 when no votes yet.
    ///      Read `totalVotes` first — a score from 1 vote is not a verdict.
    function getScore(
        uint256 projectId
    )
        external
        view
        returns (uint32 safeVotes, uint32 riskyVotes, uint32 totalVotes, uint32 scoreBps)
    {
        Project storage p = _project(projectId);
        safeVotes = p.safeVotes;
        riskyVotes = p.riskyVotes;
        totalVotes = safeVotes + riskyVotes;
        scoreBps = totalVotes == 0
            ? 0
            : uint32((uint256(safeVotes) * 10000) / uint256(totalVotes));
    }

    /// @notice True when `account` currently holds at least one Agent ID.
    function isAgentIdHolder(address account) external view returns (bool) {
        return agentId.balanceOf(account) > 0;
    }

    // ---------------------------------------------------------------
    // Owner moderation (the only owner powers — see contract notice)
    // ---------------------------------------------------------------

    function setProjectActive(
        uint256 projectId,
        bool active
    ) external onlyOwner {
        Project storage p = _project(projectId);
        p.active = active;
        emit ProjectActiveSet(projectId, active);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "owner=0");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    // ---------------------------------------------------------------
    // Internals
    // ---------------------------------------------------------------

    function _project(
        uint256 projectId
    ) internal view returns (Project storage p) {
        if (projectId == 0 || projectId > _projects.length) {
            revert ProjectNotFound(projectId);
        }
        p = _projects[projectId - 1];
    }

    function _markInteracted(address account) internal {
        if (!hasInteracted[account]) {
            hasInteracted[account] = true;
            uniqueInteractors += 1;
        }
    }

    /// @notice This registry never takes custody of funds. Reject plain
    ///         transfers so BNB cannot get stuck here by accident.
    receive() external payable {
        revert("AgentGuard: no funds accepted");
    }
}
