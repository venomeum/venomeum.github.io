// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * Venomeum Names (VNAME) — a soul-bound on-chain name service, ENS-style.
 *
 * Each registered label (e.g. "venom") mints one ERC-721-style NFT whose
 * full name is label + ".vmh" (venom.vmh). Names are SOUL-BOUND: they can
 * be minted (on register) and burned (by their owner), but never
 * transferred or approved — transferFrom / safeTransferFrom / approve /
 * setApprovalForAll always revert.
 *
 * Registration is permissionless and free. Labels are 3–32 chars of
 * [a-z0-9-], not starting or ending with '-'.
 *
 * Resolution: resolve(label) -> owner address; primaryNameOf(address)
 * -> the address's primary full name ("label.vmh").
 */
contract VenomeumNames {
    string public constant name = "Venomeum Names";
    string public constant symbol = "VNAME";
    string public constant tld = "vmh";

    address public owner;

    uint256 public nextTokenId = 1;
    uint256 public totalNames;

    mapping(uint256 => address) private _owners;
    mapping(address => uint256) private _balances;
    mapping(string => address) private _labelOwner;
    mapping(string => uint256) private _labelTokenId;
    mapping(uint256 => string) private _tokenLabel;
    mapping(address => string) private _primaryLabel;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Registered(string label, address indexed owner, uint256 indexed tokenId);
    event Burned(string label, address indexed owner, uint256 indexed tokenId);
    event PrimarySet(address indexed owner, string label);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "NOT_OWNER");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "ZERO_ADDRESS");
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    // ------------------------------------------------------------------
    // Registration
    // ------------------------------------------------------------------

    function _validateLabel(string calldata label) internal pure {
        bytes memory b = bytes(label);
        require(b.length >= 3 && b.length <= 32, "LABEL_LENGTH");
        require(b[0] != 0x2d && b[b.length - 1] != 0x2d, "LABEL_HYPHEN_EDGE");
        for (uint256 i = 0; i < b.length; i++) {
            bytes1 c = b[i];
            bool ok = (c >= 0x61 && c <= 0x7a) || (c >= 0x30 && c <= 0x39) || c == 0x2d;
            require(ok, "LABEL_CHARSET");
        }
    }

    function register(string calldata label) external returns (uint256 tokenId) {
        _validateLabel(label);
        require(_labelOwner[label] == address(0), "LABEL_TAKEN");

        tokenId = nextTokenId++;
        _owners[tokenId] = msg.sender;
        _balances[msg.sender] += 1;
        _labelOwner[label] = msg.sender;
        _labelTokenId[label] = tokenId;
        _tokenLabel[tokenId] = label;
        totalNames += 1;

        // First name an address registers becomes its primary name.
        if (bytes(_primaryLabel[msg.sender]).length == 0) {
            _primaryLabel[msg.sender] = label;
        }

        emit Transfer(address(0), msg.sender, tokenId);
        emit Registered(label, msg.sender, tokenId);
    }

    function burn(uint256 tokenId) external {
        require(_owners[tokenId] == msg.sender, "NOT_TOKEN_OWNER");
        string memory label = _tokenLabel[tokenId];

        delete _owners[tokenId];
        _balances[msg.sender] -= 1;
        delete _labelOwner[label];
        delete _labelTokenId[label];
        delete _tokenLabel[tokenId];
        totalNames -= 1;

        if (_hashEquals(_primaryLabel[msg.sender], label)) {
            delete _primaryLabel[msg.sender];
        }

        emit Transfer(msg.sender, address(0), tokenId);
        emit Burned(label, msg.sender, tokenId);
    }

    function _hashEquals(string memory a, string memory b) internal pure returns (bool) {
        return keccak256(bytes(a)) == keccak256(bytes(b));
    }

    // ------------------------------------------------------------------
    // Resolution
    // ------------------------------------------------------------------

    function resolve(string calldata label) external view returns (address) {
        return _labelOwner[label];
    }

    function ownerOfLabel(string calldata label) external view returns (address) {
        return _labelOwner[label];
    }

    function tokenIdOfLabel(string calldata label) external view returns (uint256) {
        return _labelTokenId[label];
    }

    function labelOf(uint256 tokenId) external view returns (string memory) {
        require(_owners[tokenId] != address(0), "NONEXISTENT_TOKEN");
        return _tokenLabel[tokenId];
    }

    function fullNameOf(uint256 tokenId) external view returns (string memory) {
        require(_owners[tokenId] != address(0), "NONEXISTENT_TOKEN");
        return string(abi.encodePacked(_tokenLabel[tokenId], ".", tld));
    }

    function primaryNameOf(address account) external view returns (string memory) {
        string memory label = _primaryLabel[account];
        if (bytes(label).length == 0) return "";
        return string(abi.encodePacked(label, ".", tld));
    }

    function primaryLabelOf(address account) external view returns (string memory) {
        return _primaryLabel[account];
    }

    function setPrimary(string calldata label) external {
        require(_labelOwner[label] == msg.sender, "NOT_LABEL_OWNER");
        _primaryLabel[msg.sender] = label;
        emit PrimarySet(msg.sender, label);
    }

    function isAvailable(string calldata label) external view returns (bool) {
        return _labelOwner[label] == address(0);
    }

    // ------------------------------------------------------------------
    // ERC-721 surface (soul-bound)
    // ------------------------------------------------------------------

    function balanceOf(address account) external view returns (uint256) {
        require(account != address(0), "ZERO_ADDRESS");
        return _balances[account];
    }

    function ownerOf(uint256 tokenId) external view returns (address) {
        address o = _owners[tokenId];
        require(o != address(0), "NONEXISTENT_TOKEN");
        return o;
    }

    function getApproved(uint256) external pure returns (address) {
        return address(0);
    }

    function isApprovedForAll(address, address) external pure returns (bool) {
        return false;
    }

    function approve(address, uint256) external pure {
        revert("SOULBOUND");
    }

    function setApprovalForAll(address, bool) external pure {
        revert("SOULBOUND");
    }

    function transferFrom(address, address, uint256) external pure {
        revert("SOULBOUND");
    }

    function safeTransferFrom(address, address, uint256) external pure {
        revert("SOULBOUND");
    }

    function safeTransferFrom(address, address, uint256, bytes calldata) external pure {
        revert("SOULBOUND");
    }

    function supportsInterface(bytes4 interfaceId) external pure returns (bool) {
        return interfaceId == 0x80ac58cd   // ERC-721
            || interfaceId == 0x5b5e139f   // ERC-721 metadata
            || interfaceId == 0x01ffc9a7;  // ERC-165
    }

    // ------------------------------------------------------------------
    // Metadata
    // ------------------------------------------------------------------

    function tokenURI(uint256 tokenId) external view returns (string memory) {
        require(_owners[tokenId] != address(0), "NONEXISTENT_TOKEN");
        string memory full = string(abi.encodePacked(_tokenLabel[tokenId], ".", tld));

        string memory svg = string(abi.encodePacked(
            "<svg xmlns='http://www.w3.org/2000/svg' width='500' height='500'>",
            "<rect width='100%' height='100%' fill='black'/>",
            "<text x='50%' y='50%' fill='white' font-family='monospace' font-size='30' ",
            "text-anchor='middle' dominant-baseline='middle'>",
            full,
            "</text></svg>"
        ));

        string memory json = string(abi.encodePacked(
            '{"name": "', full, '", ',
            '"description": "Venomeum Names - a soul-bound on-chain name (', full, ').", ',
            '"image": "data:image/svg+xml;base64,', _base64Encode(bytes(svg)), '"}'
        ));

        return string(abi.encodePacked("data:application/json;base64,", _base64Encode(bytes(json))));
    }

    // Standard base64 encoder (RFC 4648), hand-rolled in plain Solidity.
    function _base64Encode(bytes memory data) internal pure returns (string memory) {
        if (data.length == 0) return "";
        bytes memory table = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        uint256 encodedLen = 4 * ((data.length + 2) / 3);
        bytes memory result = new bytes(encodedLen);
        uint256 j = 0;
        for (uint256 i = 0; i < data.length; i += 3) {
            uint256 a = uint8(data[i]);
            uint256 b = i + 1 < data.length ? uint8(data[i + 1]) : 0;
            uint256 c = i + 2 < data.length ? uint8(data[i + 2]) : 0;
            uint256 triple = (a << 16) | (b << 8) | c;
            result[j++] = table[(triple >> 18) & 0x3F];
            result[j++] = table[(triple >> 12) & 0x3F];
            result[j++] = i + 1 < data.length ? table[(triple >> 6) & 0x3F] : bytes1("=");
            result[j++] = i + 2 < data.length ? table[triple & 0x3F] : bytes1("=");
        }
        return string(result);
    }
}
