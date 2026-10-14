"""Write compact static-evidence ledger from the offline bootstrap investigation."""
from pathlib import Path
import hashlib,json,sys,zlib,struct
from extract_npk import Marshal2,parse_npk,decode_entry
from neox_rotor import decrypt,encrypt,KEY,DN,DT,DF

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/bootstrap'
sha=lambda b:hashlib.sha256(b).hexdigest()

def main():
    native=(OUT/'extracted/lib/armeabi-v7a/libclient.so').read_bytes()
    npk=(ROOT/'analysis/assets/extracted/assets/script.npk').read_bytes()
    hdr,entries=parse_npk(npk)
    raw=decode_entry(npk,entries[0]);dec=decrypt(raw);afterz=zlib.decompress(dec)
    marsh=bytes((b^154 if i<128 else b) for i,b in enumerate(afterz))[::-1]
    reader=Marshal2(marsh);obj=reader.obj();assert reader.pos==len(marsh)
    assert decrypt(encrypt(bytes(range(256))*3))==bytes(range(256))*3
    keys=[]
    for name,pos,table,value in [('dn',0xec4ca4,0x2b04628,DN),('dt',0xec4ce0,0x2b04638,DT),('df',0xec4d14,0x2b04648,DF)]:
        assert native[pos:pos+len(value)+1]==value+b'\0'
        ptr,fn,flags,doc=struct.unpack_from('<4I',native,table)
        keys.append({'name':name,'value_ascii':value.decode('ascii'),'value_file_offset':hex(pos),
                     'py_method_table_offset':hex(table),'name_pointer':hex(ptr),'thumb_function_pointer':hex(fn),'flags':flags,'doc_pointer':hex(doc)})
    index=json.loads((ROOT/'analysis/assets/decoded/script/index.json').read_text('utf8'))
    selected=[246,299,996,1187,1256,3091,3637,4240,4267,6521,6944,7182,7329,8758,9228,9509]
    facts=[
      {'id':'B01','classification':'observed_static_and_decoder_validation','claim':'The rotor key and script decoding pipeline were recovered and validated against packaged script data.',
       'evidence':['redirect_keys.thumb.txt','scripts are safely parsed as Python 2 marshal, never executed'],
       'pipeline':['rotor.decrypt with reset per entry','zlib.decompress','xor first 128 decoded bytes with 154','reverse entire byte sequence','parse Python 2 marshal as inert data']},
      {'id':'B02','classification':'observed_static','claim':'Seven embedded engine/game protobuf FileDescriptorProto records recover message and service wire schemas.',
       'evidence':['proto/inventory.json','proto/*.proto.bin','client_gate_descriptor.thumb.txt'],
       'cross_check':'client_gate.proto descriptor offset 0x28d0030 and size 0x65c agree with native AddDescriptorsImpl pointer and movw r1,#0x65c.'},
      {'id':'B03','classification':'observed_static_reference_implementation','claim':'Python MobileRpcChannel frames a serialized protobuf with uint32le(body length) and uint16le(method index).',
       'module_index':8758,'function':'MobileRpcChannel.CallMethod','source_line':100,
       'bytecode_ranges':['0x27..0x34 total_len=len(proto)+2','0x46..0x67 pack length + method index + proto'],
       'frame':'uint32le(2+protobuf.length) || uint16le(method_descriptor.index) || protobuf',
       'method_index':'assert index < 65535; unsigned H packing also rejects negative values',
       'limits':'MobileRequest accepts body length 1..16777215; RpcChannel then rejects body length <2. End-to-end minimal body 2; minimal full frame 6; protobuf payload may be empty.',
       'runtime_limit':'The shipping CConnector instantiates AsioGateClient, so native framing/stream behavior still needs correlation.'},
      {'id':'B04','classification':'observed_static','claim':'Shipping script CConnector selects AsioGateClient with encryption and compression enabled.',
       'module_index':9509,'function':'<module> / _Connector.connect','bytecode_ranges':['module 0xce..0xed','connect 0x92..0xa4'],
       'client_config':{'enforce_encryption':1,'use_keyczar':0,'loginkeypath':'res/test_rsa.pub','zipped_channel':1}},
      {'id':'B05','classification':'observed_static','claim':'AsioGateClient requests a seed then sends RSA-OAEP encrypted SessionKey metadata and schedules native stream encryption.',
       'module_indices':[299,4267,3637],
       'sequence':['send_seed_request','seed_reply(seed)','SessionKey(header padding, SHA(random 32 bytes).digest(), seed, tail padding)','delay_enable_encrypt(session_key)','send_session_key(keyencrypter.encrypte(serialized SessionKey))','session_key_ok -> connect_server'],
       'padding':'default random header and tail lengths 16..64',
       'algorithm_evidence':'LoginKeyEncrypterNokeyczar uses Crypto.PublicKey.RSA.importKey and Crypto.Cipher.PKCS1_OAEP.new().encrypt.',
       'reference_only':'Python GateClient installs ARC4Crypter. Native Asio stream cipher state has not yet been disassembled or observed.'},
      {'id':'B06','classification':'observed_static_reference_implementation','claim':'Python Compressor holds zlib compressobj/decompressobj state across messages and calls compress(data)+flush(2).','module_index':9228},
      {'id':'B07','classification':'observed_static_configuration','claim':'Chinese publish build identifies project u1 and carries HTTP server-discovery endpoints.',
       'module_indices':[4240,6944,1256,246],
       'app_internal_id':'u1','client_version':'1.222180.224889','package_branch':'publish',
       'server_list_domain':'https://u1.update.netease.com',
       'server_list_paths':['/server_list_normal.txt','/server_list_all.txt','/server_list_apple_review.txt'],
       'sdk_login_base':'https://mgb.matrix.netease.com/u1/gb/',
       'network_access':'No requests were made to these game/SDK endpoints.'},
      {'id':'B08','classification':'observed_static_parser','claim':'parseOneServerInfo splits a row by literal spaces and reads ten columns.',
       'module_index':246,'function':'parseOneServerInfo','source_line':152,
       'columns':['zone (str)','numberSt (int)','netSt (int)','serverSt (int)','name (str)','oriName (str)','ipAndPort (str)','groupID (int)','logicID (int)','group (str)'],
       'other_rows':'For a nonempty row with fewer than 10 columns, returns (Network, first-token[9:].strip()); empty row returns (None,None).',
       'ip_selection':'getServerListByContent groups rows and splits ipAndPort using colon before int(port).',
       'local_fallback':'getServerIpInfo carries default 127.0.0.1:4000, but enabling its branch is not established here.'},
      {'id':'B09','classification':'observed_static_application_logic','claim':'Account entity provides login request and callbacks onUnisdkLoginback/onLoginOK/onLoginFailed; create_entity and later business RPCs are necessary beyond transport.',
       'module_index':3091,'unknown':'Exact minimum state needed for login, lobby, and battle is not implemented or runtime-tested.'}
    ]
    report={'scope':'Offline APK/bootstrap/protocol investigation; original APK unmodified. No APK execution, no old-game-service requests, no global installs.',
            'native_member':'lib/armeabi-v7a/libclient.so','native_sha256':sha(native),'npk_sha256':sha(npk),
            'keys':keys,'rotor_key_formula':"DN*5 + DT*6 + '@' + (DT+DN+DF)*4 + '#!' + DF*3 + '^%'",'rotor_key_sha256':sha(KEY),
            'rotor_source':{'url':'https://raw.githubusercontent.com/python/cpython/v2.3.7/Modules/rotormodule.c','local':'analysis/bootstrap/cpython-v2.3.7-rotormodule.c','sha256':sha((OUT/'cpython-v2.3.7-rotormodule.c').read_bytes())},
            'decoder_validation':{'npk_index':0,'cipher_sha256':sha(raw),'decrypted_prefix':dec[:16].hex(),'marshal_sha256':sha(marsh),'marshal_bytes_consumed':reader.pos,'filename':obj['filename'].decode('utf8'),'synthetic_roundtrip_bytes':768},
            'module_evidence':[index[i] for i in selected], 'findings':facts,
            'unresolved':['Native transport framing and cipher/compression byte ordering require disassembly or local runtime correlation.',
                          'Local replacement service needs a chosen strategy for replacing the client-side RSA public key or modifying its own encryption configuration.',
                          'Server-list fetch verification, update/patch gates, SDK login, and minimum entity/state startup need local runtime testing.',
                          'Original server data and account progress are not recoverable from these static declarations alone.',
                          'The partial NeoX opcode map is not a full decompiler. Recovered .proto text omits options/extensions but raw descriptor binaries retain them.']}
    path=OUT/'findings.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(path)

if __name__=='__main__':main()
