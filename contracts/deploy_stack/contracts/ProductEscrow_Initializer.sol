// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

// ── Role-specific errors ──
error NotBuyer();
error NotSeller();
error NotTransporter();
error NotFactory();

// ── Business logic errors ──
error InvalidPhase();
error InvalidProductId();
error InvalidOwnerAddress();
error EmptyName();
error ZeroPriceCommitment();
error AlreadyInitialized();
error AlreadyPurchased();
error AlreadyDelivered();
error AlreadyExists();
error AlreadyPaid();
error AlreadySelected();

// ── State validation errors ──
error WrongPhase();
error TransporterNotSet();
error BidCapReached();
error NotRegistered();
error IncorrectFee();
error NotATransporter();
error OwnerCannotPurchase();
error NotPurchased();
error SellerWindowNotExpired();
error SellerWindowExpired();
error BiddingWindowNotExpired();
error NotYetTimeout();

// ── Transfer and payment errors ──
error TransferFailed(address to, uint256 amount);
error RefundFailed();
error IncorrectDeliveryFee();

// ── Railgun and memo errors ──
error WrongProductId();
error ZeroMemoHash();
error ZeroTxRef();
error MemoAlreadyUsed();
error PaymentAlreadyRecorded();
error NotParticipant();

// ── Bond errors ──
error BondAlreadyDeposited();
error BondNotDeposited();
error HashMismatch();
error InsufficientBond();
error DeliveryWindowExpired();

contract ProductEscrow_Initializer is ReentrancyGuard {

    // ═══════════════════════════════════════════════════════════════════
    //  Storage - Group 1
    // ═══════════════════════════════════════════════════════════════════
    uint256 public id;
    string public name;
    bytes32 public priceCommitment;

    // ═══════════════════════════════════════════════════════════════════
    //  Storage - Group 2 (addresses)
    // ═══════════════════════════════════════════════════════════════════
    address payable public owner;
    address payable public buyer;
    address payable public transporter;

    // ═══════════════════════════════════════════════════════════════════
    //  Storage - Group 3 (packed: enum + timestamps + booleans + counters)
    // ═══════════════════════════════════════════════════════════════════
    enum Phase { Listed, Purchased, OrderConfirmed, Bound, Delivered, Expired }
    Phase public phase;
    uint64 public purchaseTimestamp;
    uint64 public orderConfirmedTimestamp;
    uint64 public boundTimestamp;
    bool public purchased;
    bool public delivered;
    uint32 public transporterCount;

    // ═══════════════════════════════════════════════════════════════════
    //  Constants
    // ═══════════════════════════════════════════════════════════════════
    uint32 public constant SELLER_WINDOW = 2 days;
    uint32 public constant BID_WINDOW = 2 days;
    uint32 public constant DELIVERY_WINDOW = 2 days;
    uint8 public constant MAX_BIDS = 20;

    // ═══════════════════════════════════════════════════════════════════
    //  Storage - Separate slots (larger values)
    // ═══════════════════════════════════════════════════════════════════
    uint256 public deliveryFee;
    uint256 public sellerBond;
    uint256 public bondAmount;
    bytes32 public vcHash;

    // ═══════════════════════════════════════════════════════════════════
    //  Mappings and arrays
    // ═══════════════════════════════════════════════════════════════════
    mapping(address => uint256) public securityDeposits;   // Transporter bond deposits
    mapping(address => uint256) public transporters;       // Transporter fee bids
    mapping(address => bool) public isTransporter;
    address[] public transporterAddresses;

    // Initialization and factory
    bool private _initialized;
    address public factory;
    bool private stopped;

    // Railgun integration state
    mapping(bytes32 => bool) public privatePayments;
    mapping(uint256 => bytes32) public productMemoHashes;
    mapping(uint256 => bytes32) public productRailgunTxRefs;
    mapping(bytes32 => bool) public usedMemoHash;
    mapping(uint256 => address) public productPaidBy;

    // ═══════════════════════════════════════════════════════════════════
    //  Modifiers
    // ═══════════════════════════════════════════════════════════════════
    modifier onlyBuyer() {
        if (msg.sender != buyer) revert NotBuyer();
        _;
    }

    modifier onlySeller() {
        if (msg.sender != owner) revert NotSeller();
        _;
    }

    modifier onlyTransporter() {
        if (msg.sender != transporter) revert NotTransporter();
        _;
    }

    modifier onlyFactory() {
        if (msg.sender != factory && factory != address(0)) revert NotFactory();
        _;
    }

    modifier transporterSet() {
        if (transporter == address(0)) revert TransporterNotSet();
        _;
    }

    modifier whenNotStopped() {
        require(!stopped, "stopped");
        _;
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Events
    // ═══════════════════════════════════════════════════════════════════
    event OrderConfirmed(address indexed buyer, address indexed seller, uint256 indexed productId, bytes32 priceCommitment, string vcCID, uint256 timestamp);
    event DeliveryConfirmed(address indexed buyer, address indexed transporter, address indexed seller, uint256 productId, bytes32 priceCommitment, uint256 timestamp);
    event TransporterCreated(address indexed transporter, uint256 indexed productId, uint256 timestamp);
    event TransporterSelected(uint256 indexed productId, address indexed transporter, uint256 timestamp);
    event FundsTransferred(address indexed to, uint256 indexed productId, uint256 timestamp);
    event PenaltyApplied(address indexed to, uint256 indexed productId, string reason, uint256 timestamp);
    event DeliveryTimeoutEvent(address indexed caller, uint256 indexed productId, uint256 time, uint256 timestamp);
    event SellerTimeoutEvent(address indexed caller, uint256 indexed productId, uint256 time, uint256 timestamp);
    event PhaseChanged(uint256 indexed productId, Phase indexed from, Phase indexed to, address actor, uint256 timestamp, bytes32 ref);
    event BidWithdrawn(address indexed transporter, uint256 indexed productId, uint256 timestamp);

    // Comprehensive product state change event for frontend indexing
    event ProductStateChanged(
        uint256 indexed productId,
        address indexed seller,
        address indexed buyer,
        Phase phase,
        uint256 timestamp,
        bytes32 priceCommitment,
        bool purchased,
        bool delivered
    );

    // Railgun integration events
    event PaidPrivately(uint256 indexed productId, bytes32 memoHash, bytes32 railgunTxRef, uint256 timestamp);
    event PrivatePaymentRecorded(uint256 indexed productId, bytes32 memoHash, bytes32 railgunTxRef, address indexed recorder, uint256 timestamp);
    event PurchasedPrivate(address indexed buyer, bytes32 memoHash, bytes32 railgunTxRef);

    // Bond events
    event SellerBondDeposited(uint256 indexed productId, address indexed seller, uint256 amount, uint256 timestamp);
    event TransporterBondDeposited(uint256 indexed productId, address indexed transporter, uint256 amount, uint256 timestamp);
    event VcHashStored(uint256 indexed productId, bytes32 vcHash, string vcCID, uint256 timestamp);
    event BondSlashed(uint256 indexed productId, address indexed from, address indexed to, uint256 amount, string reason, uint256 timestamp);
    event BondReturned(uint256 indexed productId, address indexed to, uint256 amount, uint256 timestamp);
    event BuyerDesignated(uint256 indexed productId, address indexed buyer, uint256 timestamp);

    // ═══════════════════════════════════════════════════════════════════
    //  Initialization
    // ═══════════════════════════════════════════════════════════════════

    /// @notice Initialize the escrow clone. Called by factory with seller bond forwarded as msg.value.
    /// @param _id Product ID (must be > 0)
    /// @param _name Product name
    /// @param _priceCommitment Confidential price commitment (keccak256 hash)
    /// @param _owner Seller address
    /// @param _bondAmount Required bond amount (from factory config)
    /// @param _factory Factory contract address
    function initialize(
        uint256 _id,
        string memory _name,
        bytes32 _priceCommitment,
        address _owner,
        uint256 _bondAmount,
        address _factory
    ) external payable {
        if (_initialized) revert AlreadyInitialized();
        if (_owner == address(0)) revert InvalidOwnerAddress();
        if (bytes(_name).length == 0) revert EmptyName();
        if (_priceCommitment == bytes32(0)) revert ZeroPriceCommitment();
        if (_id == 0) revert InvalidProductId();
        if (msg.sender != _factory) revert NotFactory();
        if (msg.value != _bondAmount) revert InsufficientBond();

        _initialized = true;
        factory = _factory;

        id = _id;
        name = _name;
        priceCommitment = _priceCommitment;
        owner = payable(_owner);
        bondAmount = _bondAmount;
        sellerBond = msg.value;
        purchased = false;
        buyer = payable(address(0));
        phase = Phase.Listed;

        emit SellerBondDeposited(_id, _owner, msg.value, block.timestamp);
        emit ProductStateChanged(_id, owner, buyer, phase, block.timestamp, _priceCommitment, purchased, delivered);
        emit PhaseChanged(_id, Phase.Listed, Phase.Listed, msg.sender, block.timestamp, bytes32(0));
    }

    /// @notice Seller designates the only address allowed to record private payment.
    function designateBuyer(address payable _buyer) external onlySeller whenNotStopped {
        if (phase != Phase.Listed) revert WrongPhase();
        if (_buyer == address(0) || _buyer == owner) revert NotParticipant();
        if (purchased) revert AlreadyPurchased();
        buyer = _buyer;
        emit BuyerDesignated(id, _buyer, block.timestamp);
        emit ProductStateChanged(id, owner, buyer, phase, block.timestamp, priceCommitment, purchased, delivered);
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Core Lifecycle Functions
    // ═══════════════════════════════════════════════════════════════════

    /// @notice Record a private Railgun payment. First valid caller becomes the buyer (FCFS).
    /// @param _productId Must match this product's ID
    /// @param _memoHash Railgun memo hash (non-zero)
    /// @param _railgunTxRef Railgun transaction reference (non-zero)
    function recordPrivatePayment(uint256 _productId, bytes32 _memoHash, bytes32 _railgunTxRef) external nonReentrant whenNotStopped {
        if (_productId != id) revert WrongProductId();
        if (_memoHash == bytes32(0)) revert ZeroMemoHash();
        if (_railgunTxRef == bytes32(0)) revert ZeroTxRef();
        if (phase != Phase.Listed) revert AlreadyPurchased();
        if (msg.sender == owner) revert OwnerCannotPurchase();

        if (productMemoHashes[id] != bytes32(0)) revert AlreadyPaid();
        if (usedMemoHash[_memoHash]) revert MemoAlreadyUsed();
        if (privatePayments[_memoHash]) revert PaymentAlreadyRecorded();

        // FCFS marketplace behavior: first successful buyer becomes the on-chain buyer.
        buyer = payable(msg.sender);

        purchased = true;
        purchaseTimestamp = uint64(block.timestamp);

        privatePayments[_memoHash] = true;
        usedMemoHash[_memoHash] = true;
        productMemoHashes[id] = _memoHash;
        productRailgunTxRefs[id] = _railgunTxRef;
        productPaidBy[id] = msg.sender;

        Phase oldPhase = phase;
        phase = Phase.Purchased;

        emit PurchasedPrivate(msg.sender, _memoHash, _railgunTxRef);
        emit PhaseChanged(id, oldPhase, phase, msg.sender, block.timestamp, _memoHash);
        emit ProductStateChanged(id, owner, buyer, phase, block.timestamp, priceCommitment, purchased, delivered);
        emit PrivatePaymentRecorded(id, _memoHash, _railgunTxRef, msg.sender, block.timestamp);
    }

    /// @notice Seller confirms order, uploads VC to IPFS, stores vcHash on-chain.
    /// @param vcCID The IPFS CID of the Verifiable Credential
    function confirmOrder(string calldata vcCID) external onlySeller nonReentrant whenNotStopped {
        if (phase != Phase.Purchased) revert WrongPhase();
        if (!purchased) revert NotPurchased();
        if (block.timestamp > purchaseTimestamp + SELLER_WINDOW) revert SellerWindowExpired();

        orderConfirmedTimestamp = uint64(block.timestamp);
        phase = Phase.OrderConfirmed;

        // Store hash only, emit full CID in event
        vcHash = keccak256(bytes(vcCID));

        emit VcHashStored(id, vcHash, vcCID, block.timestamp);
        emit OrderConfirmed(buyer, owner, id, priceCommitment, vcCID, block.timestamp);
        emit PhaseChanged(id, Phase.Purchased, Phase.OrderConfirmed, msg.sender, block.timestamp, vcHash);
    }

    /// @notice Transporter registers a bid with fee quote and stakes bond.
    /// @param _feeInWei Delivery fee bid in wei
    function createTransporter(uint256 _feeInWei) public payable nonReentrant whenNotStopped {
        if (phase != Phase.OrderConfirmed) revert WrongPhase();
        if (transporterCount >= MAX_BIDS) revert BidCapReached();
        if (isTransporter[msg.sender]) revert AlreadyExists();
        if (_feeInWei == 0) revert IncorrectFee();
        if (msg.value != bondAmount) revert InsufficientBond();

        transporters[msg.sender] = _feeInWei;
        isTransporter[msg.sender] = true;
        transporterAddresses.push(msg.sender);
        securityDeposits[msg.sender] = msg.value;

        unchecked { transporterCount++; }

        emit TransporterCreated(msg.sender, id, block.timestamp);
        emit TransporterBondDeposited(id, msg.sender, msg.value, block.timestamp);
    }

    /// @notice Seller selects a transporter and deposits the delivery fee.
    /// @param _transporter Address of the winning transporter
    function setTransporter(address payable _transporter) external payable onlySeller nonReentrant whenNotStopped {
        if (phase != Phase.OrderConfirmed) revert WrongPhase();
        if (block.timestamp > orderConfirmedTimestamp + BID_WINDOW) revert BiddingWindowNotExpired();
        if (!isTransporter[_transporter]) revert NotATransporter();
        if (msg.value != transporters[_transporter]) revert IncorrectDeliveryFee();

        deliveryFee = msg.value;
        transporter = _transporter;
        boundTimestamp = uint64(block.timestamp);

        Phase oldPhase = phase;
        phase = Phase.Bound;

        emit PhaseChanged(id, oldPhase, phase, msg.sender, block.timestamp, bytes32(0));
        emit TransporterSelected(id, _transporter, block.timestamp);
    }

    /// @notice Transporter confirms delivery by providing the VC hash.
    /// @dev Verifies hash matches stored vcHash. Releases all bonds and fee.
    /// @param hash keccak256(vcCID) that the transporter verified with the buyer
    function confirmDelivery(bytes32 hash) external onlyTransporter nonReentrant whenNotStopped {
        if (phase != Phase.Bound) revert WrongPhase();
        if (delivered) revert AlreadyDelivered();
        if (hash != vcHash) revert HashMismatch();
        if (block.timestamp > boundTimestamp + DELIVERY_WINDOW) revert DeliveryWindowExpired();

        // Effects: update state before transfers
        delivered = true;
        Phase oldPhase = phase;
        phase = Phase.Delivered;

        // Cache and zero state before transfers (checks-effects-interactions)
        uint256 _sellerBond = sellerBond;
        uint256 _transporterBond = securityDeposits[transporter];
        uint256 _deliveryFee = deliveryFee;
        sellerBond = 0;
        securityDeposits[transporter] = 0;
        deliveryFee = 0;

        // Return seller bond
        (bool sentSeller, ) = owner.call{value: _sellerBond}("");
        if (!sentSeller) revert TransferFailed(owner, _sellerBond);
        emit BondReturned(id, owner, _sellerBond, block.timestamp);

        // Return transporter bond + pay delivery fee
        uint256 transporterPayout = _transporterBond + _deliveryFee;
        (bool sentTransporter, ) = transporter.call{value: transporterPayout}("");
        if (!sentTransporter) revert TransferFailed(transporter, transporterPayout);
        emit BondReturned(id, transporter, _transporterBond, block.timestamp);
        emit FundsTransferred(transporter, id, block.timestamp);

        emit DeliveryConfirmed(buyer, transporter, owner, id, priceCommitment, block.timestamp);
        emit PhaseChanged(id, oldPhase, phase, msg.sender, block.timestamp, hash);
        emit ProductStateChanged(id, owner, buyer, phase, block.timestamp, priceCommitment, purchased, delivered);
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Timeout Functions (permissionless - anyone can call after window)
    // ═══════════════════════════════════════════════════════════════════

    /// @notice Seller failed to confirm order within window. Slash seller bond to buyer.
    function sellerTimeout() public nonReentrant whenNotStopped {
        if (phase != Phase.Purchased) revert WrongPhase();
        if (block.timestamp <= purchaseTimestamp + SELLER_WINDOW) revert SellerWindowNotExpired();

        Phase oldPhase = phase;
        phase = Phase.Expired;

        // Cache and zero before transfer
        uint256 _sellerBond = sellerBond;
        sellerBond = 0;

        // Slash seller bond to buyer
        if (_sellerBond > 0) {
            (bool sent, ) = buyer.call{value: _sellerBond}("");
            if (!sent) revert TransferFailed(buyer, _sellerBond);
            emit BondSlashed(id, owner, buyer, _sellerBond, "Seller failed to confirm order", block.timestamp);
        }

        emit PhaseChanged(id, oldPhase, phase, msg.sender, block.timestamp, bytes32(0));
        emit SellerTimeoutEvent(msg.sender, id, block.timestamp, block.timestamp);
    }

    /// @notice No transporter selected within bidding window. Return seller bond.
    /// @dev Transporter bonds are returned individually via withdrawBid().
    function bidTimeout() public nonReentrant whenNotStopped {
        if (phase != Phase.OrderConfirmed) revert WrongPhase();
        if (block.timestamp <= orderConfirmedTimestamp + BID_WINDOW) revert BiddingWindowNotExpired();

        Phase oldPhase = phase;
        phase = Phase.Expired;

        // Cache and zero before transfer
        uint256 _sellerBond = sellerBond;
        sellerBond = 0;

        // Return seller bond (not seller's fault)
        if (_sellerBond > 0) {
            (bool sent, ) = owner.call{value: _sellerBond}("");
            if (!sent) revert TransferFailed(owner, _sellerBond);
            emit BondReturned(id, owner, _sellerBond, block.timestamp);
        }

        emit PhaseChanged(id, oldPhase, phase, msg.sender, block.timestamp, bytes32(0));
    }

    /// @notice Transporter failed to deliver within window. Slash transporter bond to seller.
    function deliveryTimeout() public nonReentrant whenNotStopped {
        if (phase != Phase.Bound) revert WrongPhase();
        if (block.timestamp <= boundTimestamp + DELIVERY_WINDOW) revert NotYetTimeout();

        Phase oldPhase = phase;
        phase = Phase.Expired;

        // Cache and zero all before transfers
        uint256 _sellerBond = sellerBond;
        uint256 _transporterBond = securityDeposits[transporter];
        uint256 _deliveryFee = deliveryFee;
        sellerBond = 0;
        securityDeposits[transporter] = 0;
        deliveryFee = 0;

        // Return seller bond
        if (_sellerBond > 0) {
            (bool sent, ) = owner.call{value: _sellerBond}("");
            if (!sent) revert TransferFailed(owner, _sellerBond);
            emit BondReturned(id, owner, _sellerBond, block.timestamp);
        }

        // Slash transporter bond to seller
        uint256 slashToSeller = _transporterBond + _deliveryFee;
        if (slashToSeller > 0) {
            (bool sent, ) = owner.call{value: slashToSeller}("");
            if (!sent) revert TransferFailed(owner, slashToSeller);
            if (_transporterBond > 0) {
                emit BondSlashed(id, transporter, owner, _transporterBond, "Transporter failed to deliver", block.timestamp);
            }
            if (_deliveryFee > 0) {
                emit FundsTransferred(owner, id, block.timestamp);
            }
        }

        emit PhaseChanged(id, oldPhase, phase, msg.sender, block.timestamp, bytes32(0));
        emit DeliveryTimeoutEvent(msg.sender, id, block.timestamp, block.timestamp);
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Bid Withdrawal
    // ═══════════════════════════════════════════════════════════════════

    /// @notice Non-selected transporter withdraws bid and bond.
    /// @dev Callable in OrderConfirmed (voluntary withdrawal) or Expired (after bidTimeout/deliveryTimeout).
    function withdrawBid() public nonReentrant {
        if (phase != Phase.OrderConfirmed && phase != Phase.Expired) revert WrongPhase();
        if (transporter == msg.sender) revert AlreadySelected();

        uint256 fee = transporters[msg.sender];
        uint256 deposit = securityDeposits[msg.sender];
        if (fee == 0 && deposit == 0) revert NotRegistered();

        // Effects: zero before transfer
        transporters[msg.sender] = 0;
        securityDeposits[msg.sender] = 0;
        isTransporter[msg.sender] = false;

        unchecked { transporterCount--; }

        if (deposit > 0) {
            (bool sent, ) = payable(msg.sender).call{value: deposit}("");
            if (!sent) revert RefundFailed();
            emit BondReturned(id, msg.sender, deposit, block.timestamp);
        }

        emit BidWithdrawn(msg.sender, id, block.timestamp);
    }

    // ═══════════════════════════════════════════════════════════════════
    //  View Functions
    // ═══════════════════════════════════════════════════════════════════

    /// @notice Public getter for the stored VC hash (transporter reads this to verify delivery).
    function getVcHash() external view returns (bytes32) {
        return vcHash;
    }

    /// @notice Return all transporter addresses and their fee bids.
    function getAllTransporters() public view returns (address[] memory, uint256[] memory) {
        uint256 len = transporterAddresses.length;
        address[] memory addresses = new address[](len);
        uint256[] memory fees = new uint256[](len);

        unchecked {
            for (uint256 i = 0; i < len; i++) {
                addresses[i] = transporterAddresses[i];
                fees[i] = transporters[transporterAddresses[i]];
            }
        }

        return (addresses, fees);
    }

    /// @notice Canonical commitment computation helper (pure function for tests and UI).
    function computeCommitment(uint256 value, bytes32 salt) public pure returns (bytes32) {
        return keccak256(abi.encodePacked(value, salt));
    }

    /// @notice Check if the contract is stopped (paused by factory).
    function isStopped() external view returns (bool) {
        return stopped;
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Admin Functions
    // ═══════════════════════════════════════════════════════════════════

    /// @notice Factory can pause this escrow.
    function pauseByFactory() external {
        if (msg.sender != factory) revert NotFactory();
        stopped = true;
    }

    /// @dev Cap on number of transporter bids.
    function maxBids() internal view virtual returns (uint8) {
        return MAX_BIDS;
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Reject unexpected ETH
    // ═══════════════════════════════════════════════════════════════════
    receive() external payable {
        revert("ProductEscrow does not accept unexpected ETH");
    }

    fallback() external payable {
        revert("ProductEscrow does not accept unexpected ETH");
    }
}
