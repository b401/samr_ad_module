from impacket.dcerpc.v5 import transport,samr,epm
from impacket.nmb import NetBIOS
from socket import getaddrinfo, AF_INET



class ADOperationsError(Exception):
    def __init__(self, code):
        if code.error_code == 0xC0000022:
            print("STATUS_ACCESS_DENIED")
        elif code.error_code == 0xC0000063:
            print("Error: STATUS_USER_EXISTS")
        elif code.error_code == C000000D:
            print("Error: STATUS_INVALID_PARAMETER")
        else:
            print(code.error_code)
        
    


class Computer:
    def __init__(self, name = '', password='', description=''):
        self.name = name
        # Not implemented yet
        self.password = password
        self.description = description

# not implemented yet
class User:
    def __init__(self, name = '', password='', description=''):
        self.name = name
        self.password = password
        self.description = description

# not implemented yet
class OrganizationalUnit:
    def __init__(self, name = '', dn = '')
        self.name = name
        self.dn = password

class AD:
    def __init__(self,user: str, password: str, domain) -> None:
        self.addc = self.__lookup_addc(domain)
        self.dce = None
        self.srv_handle = None
        self.domain_handle = None
        self.creds = (user,password)
        self.sid = None

    def __bind(self,domain: str):
        stringBinding = epm.hept_map(self.addc[0], samr.MSRPC_UUID_SAMR, protocol = 'ncacn_np')
        rpccon = transport.DCERPCTransportFactory(stringBinding)
        rpccon.set_credentials(self.creds[0],self.creds[1],domain)
        dce = rpccon.get_dce_rpc()
        # connect and bind to SAMR
        dce.connect()
        dce.bind(samr.MSRPC_UUID_SAMR)
        return dce

    def __connect_SAMR(self):
        # TODO errorhandling 
        dce = self.__bind(self.addc[0])
        connect_response = samr.hSamrConnect5(dce, f'\\\\{self.addc[1]}\x00',
                samr.SAM_SERVER_ENUMERATE_DOMAINS | samr.SAM_SERVER_LOOKUP_DOMAIN)
        self.srv_handle = connect_response['ServerHandle']
        return dce

    # TODO check if successful
    # TODO error handling
    def connect(self):
        self.dce = self.__connect_SAMR()
        self.__get_domains()
            

    # TODO Allow to use different domains
    def __get_domains(self):
        samrLookupDomainresponse = samr.hSamrLookupDomainInSamServer(self.dce, self.srv_handle, self.addc[2])
        self.sid = samrLookupDomainresponse['DomainId']

    def _open_domain(self,perm = samr.DOMAIN_CREATE_USER):
        samr_response = samr.hSamrOpenDomain(self.dce, self.srv_handle, perm, self.sid)
        self.domain_handle = samr_response['DomainHandle']


    def __lookup_addc(self, domain):
        # check if domain can be resolved
        # allow custom dns
        nbt = NetBIOS()
        ip = getaddrinfo(f"{domain}", None, family=AF_INET)[0][4][0]
        nb = nbt.getnetbiosname(ip)
        # TODO 
        # - what if the domain is deeper than one level
        # - what if the nb name is different than the domain name?
        domain_nb = domain.split(".")[0].upper()
        fqdn = f"{nb}.{domain.upper()}"
        return (ip, fqdn, domain_nb, domain, nb)

    def delete_object(self,name):
        handle = self.__get_user_handle(name)
        try:
            deleteObj = samr.hSamrDeleteUser(self.dce, handle)
        except samr.DCERPCSessionError as e:
            raise ADOperationsError(e)

    def __get_rid(self,name):
        resp = samr.hSamrLookupNamesInDomain(self.dce, self.domain_handle, (name,))
        rid = resp['RelativeIds']['Element'][0]
        return rid

    def __get_user_handle(self,name):
        self._open_domain(perm = samr.DOMAIN_LOOKUP | samr.DOMAIN_LIST_ACCOUNTS | samr.DOMAIN_ADMINISTER_SERVER | samr.DELETE | samr.READ_CONTROL | samr.ACCESS_SYSTEM_SECURITY | samr.DOMAIN_WRITE_OTHER_PARAMETERS | samr.DOMAIN_WRITE_PASSWORD_PARAMS )
        request = samr.SamrOpenUser()
        request['DomainHandle'] = self.domain_handle
        request['DesiredAccess'] = \
            samr.USER_READ_GENERAL | samr.USER_READ_PREFERENCES | samr.USER_WRITE_PREFERENCES | samr.USER_READ_LOGON \
            | samr.USER_READ_ACCOUNT | samr.USER_WRITE_ACCOUNT | samr.USER_CHANGE_PASSWORD | samr.USER_FORCE_PASSWORD_CHANGE  \
            | samr.USER_LIST_GROUPS | samr.USER_READ_GROUP_INFORMATION | samr.USER_WRITE_GROUP_INFORMATION | samr.USER_ALL_ACCESS  \
            | samr.USER_READ | samr.USER_WRITE  | samr.USER_EXECUTE 
        request['UserId'] = self.__get_rid(name)
        resp = self.dce.request(request)
        return resp['UserHandle']

        


    def rename_object(self, name, newname = ''):
        try:
            # get userhandle
            userHandle = self.__get_user_handle(name)

            request = samr.SamrQueryInformationUser2()
            request['UserHandle'] = userHandle
            request['UserInformationClass'] = samr.USER_INFORMATION_CLASS.UserAccountNameInformation
            resp = self.dce.request(request)

            request = samr.SamrSetInformationUser2()
            request['UserHandle'] = userHandle
            request['UserInformationClass'] = samr.USER_INFORMATION_CLASS.UserAccountNameInformation
            request['Buffer'] = resp['Buffer']
            request['Buffer']['AccountName']['UserName'] = newname
            self.dce.request(request)
        except samr.DCERPCSessionError as e:
            raise ADOperationsError(e)

    # TODO allow different obj
    def create_object(self,obj):
        self._open_domain()
        types = {Computer:
                 {
                     'object': samr.USER_WORKSTATION_TRUST_ACCOUNT,
                     'permissions': samr.USER_FORCE_PASSWORD_CHANGE | samr.USER_WRITE_ACCOUNT |samr.DELETE
                 }
        }

        if type(obj) not in types:
            print("[x] Object does not exist")
            return False


        if type(obj) == Computer:
            try:
                samr.hSamrCreateUser2InDomain(self.dce, self.domain_handle, obj.name, types[type(obj)]['object'], types[type(obj)]['permissions'],)
            except samr.DCERPCSessionError as e:
                raise ADOperationsError(e)

        return createdObj['UserHandle']


if __name__ == '__main__':
    # Connection can be done with a normal domain user for the creation of a computer object.
    # By default domain users are capable to create up to 10 devices
    ad = AD('username','password','domain')
    # connect to addc over SAMR
    ad.connect()

    # Name of the object that should be created
    name = "testing"
    # Rename object to
    newname = "testing2"
    obj = Computer(name=name)
    # Example
    # 1. Create new computer object called testing
    ad.create_object(obj)
    # 2. Rename object to testing2
    ad.rename_object(name,newname)
    # 3. Delete object
    ad.delete_object(newname)

