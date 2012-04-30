# migrate project from youtrack to youtrack
from youtrack.connection import Connection, youtrack
#from sets import Set

#httplib2.debuglevel=4
from sync.users import UserImporter
from sync.links import LinkImporter

def main():
    try:
    #        source_url, source_login, source_password, target_url, target_login, target_password = sys.argv[1:7]
        source_url = "http://teamsys.labs.intellij.net"
        source_login = "root"
        source_password = "root"
        target_url = "http://localhost:8081"
        target_login = "root"
        target_password = "root"
        #        project_ids = sys.argv[7:]
        project_ids = ['JT']
    except BaseException, e:
        print "Usage: youtrack2youtrack source_url source_login source_password target_url target_login target_password projectId"
        return

    youtrack2youtrack(source_url, source_login, source_password, target_url, target_login, target_password, project_ids)


def create_bundle_from_bundle(source, target, bundle_name, bundle_type, user_importer):
    source_bundle = source.getBundle(bundle_type, bundle_name)
    # here we should check whether target YT has bundle with same name. But actually, to check tis, we should
    # get all bundles of every field type. So here we'll do a hack: just check if there is a bundle of bundle_type
    # type with this name, if there is bundle of another type -- there will be conflict, and we'll just exit with
    # corresponding message, as we can't proceed import anyway
    target_bundle_names = [bundle.name for bundle in target.getAllBundles(bundle_type)]
    if bundle_name in target_bundle_names:
        target_bundle = target.getBundle(bundle_type, bundle_name)
        if isinstance(source_bundle, youtrack.UserBundle):
            # get users and try to import them
            user_importer.importUsers(set(source_bundle.get_all_users()))
            # get field and calculate not existing groups
            target_bundle_group_names = [elem.name.capitalize() for elem in target_bundle.groups]
            groups_to_add = [group for group in target_bundle.groups if
                             group.name.capitalize() not in target_bundle_group_names]
            for group in groups_to_add:
                target.addValueToBundle(target_bundle, group)
                # add individual users to bundle
            source_bundle_user_logins = [elem.login.capitalize() for elem in source_bundle.users]
            users_to_add = [user for user in target_bundle.users if
                            user.login.capitalize() not in source_bundle_user_logins]
            for user in users_to_add:
                target.addValueToBundle(target_bundle, user)
            return
        target_value_names = [element.name.encode('utf-8').capitalize() for element in target_bundle.values]
        for value in [elem for elem in source_bundle.values if
                      elem.name.encode('utf-8').capitalize() not in target_value_names]:
            target.addValueToBundle(target_bundle, value)
    else:
        users = set([])
        if isinstance(source_bundle, youtrack.UserBundle):
            users = set(source_bundle.get_all_users())
        elif isinstance(source_bundle, youtrack.OwnedFieldBundle):
            users = set([source.getUser(elem.owner) for elem in source_bundle.values if elem.owner is not None])
        user_importer.importUsers(users)
        print target.createBundle(source_bundle)

def create_project_custom_field(target, field, project_id):
    params = dict([])
    if hasattr(field, "bundle"):
        params["bundle"] = field.bundle
    emptyFieldText = "No " + field.name.lower()
    if hasattr(field, "emptyFieldText"):
        emptyFieldText = field.emtyFieldText
    target.createProjectCustomFieldDetailed(project_id, field.name, emptyFieldText, params)

def youtrack2youtrack(source_url, source_login, source_password, target_url, target_login, target_password,
                      project_ids, query = ''):
    if not len(project_ids):
        print "You should sign at least one project to import"
        return

    source = Connection(source_url, source_login, source_password)
    target = Connection(target_url, target_login,
        target_password) #, proxy_info = httplib2.ProxyInfo(socks.PROXY_TYPE_HTTP, 'localhost', 8888)

    print "Import issue link types"
    for ilt in source.getIssueLinkTypes():
        try:
            print target.createIssueLinkType(ilt)
        except youtrack.YouTrackException, e:
            print e.message

    #links = []
    user_importer = UserImporter(source, target)
    link_importer = LinkImporter(source, target)

    cf_names_to_import = set([]) # names of cf prototypes that should be imported
    for project_id in project_ids:
        cf_names_to_import.update([pcf.name.capitalize() for pcf in source.getProjectCustomFields(project_id)])

    target_cf_names = [pcf.name.capitalize() for pcf in target.getCustomFields()]

    for cf_name in cf_names_to_import:
        source_cf = source.getCustomField(cf_name)
        if cf_name in target_cf_names:
            target_cf = target.getCustomField(cf_name)
            if not(target_cf.type == source_cf.type):
                print "In your target and source YT instances you have field with name [ %s ]" % cf_name.encode('utf-8')
                print "They have different types. Source field type [ %s ]. Target field type [ %s ]" %\
                      (source_cf.type, target_cf.type)
                print "exiting..."
                exit()
        else:
            if hasattr(source_cf, "defaultBundle"):
                create_bundle_from_bundle(source, target, source_cf.defaultBundle, source_cf.type, user_importer)

            target.createCustomField(source_cf)

    for projectId in project_ids:
        source = Connection(source_url, source_login, source_password)
        target = Connection(target_url, target_login,
            target_password) #, proxy_info = httplib2.ProxyInfo(socks.PROXY_TYPE_HTTP, 'localhost', 8888)
        #reset connections to avoid disconnections
        user_importer.resetConnections(source, target)
        link_importer.resetConnections(source, target)

        # copy project, subsystems, versions
        project = source.getProject(projectId)

        print "Import project [" + project.name + "]"
        lead = source.getUser(project.lead)

        print "Create project lead [" + lead.login + "]"
#        print target.createUser(lead)
        user_importer.importUsers([lead])

        try:
            target.getProject(projectId)
        except youtrack.YouTrackException:
            target.createProject(project)

        link_importer.addAvailableIssuesFrom(projectId)
        project_custom_fields = source.getProjectCustomFields(projectId)
        # create bundles and additional values
        for pcf_ref in project_custom_fields:
            pcf = source.getProjectCustomField(projectId, pcf_ref.name)
            if hasattr(pcf, "bundle"):
                create_bundle_from_bundle(source, target, pcf.bundle, source.getCustomField(pcf.name).type, user_importer)

        target_project_fields = [pcf.name for pcf in target.getProjectCustomFields(projectId)]
        for field in project_custom_fields:
            if field.name in target_project_fields:
                if hasattr(field, 'bundle'):
                    if field.bundle != target.getProjectCustomField(projectId, field.name).bundle:
                        target.deleteProjectCustomField(projectId, field.name)
                        create_project_custom_field(target, field, projectId)
            else:
                create_project_custom_field(target, field, projectId)

        # TODO: copy assignees

        # copy issues
        start = 0
        max = 20

        print "Import issues"

        while True:
            try:
                print "Get issues from " + str(start) + " to " + str(start + max)
                issues = source.getIssues(projectId, query, start, max)

                if len(issues) <= 0:
                    break

                users = set([])

                for issue in issues:
                    print "Collect users for issue [ " + issue.id + "]"

                    users.add(issue.getReporter())
                    if issue.hasAssignee(): users.add(issue.getAssignee())
                    #TODO: http://youtrack.jetbrains.net/issue/JT-6100
                    users.add(issue.getUpdater())
                    for comment in issue.getComments(): users.add(comment.getAuthor())


                    print "Collect links for issue [ " + issue.id + "]"
                    link_importer.collectLinks(issue.getLinks(True))
                    #links.extend(issue.getLinks(True))

                    # fix problem with comment.text
                    for comment in issue.getComments():
                        if not hasattr(comment, "text") or (len(comment.text) == 0):
                            setattr(comment, 'text', 'no text')

                user_importer.importUsers(users)

                print "Create issues [" + str(len(issues)) + "]"
                print target.importIssues(projectId, project.name + ' Assignees', issues)
                link_importer.addAvailableIssues(issues)

                print "Transfer attachments"
                for issue in issues:
                    attachments = issue.getAttachments()
                    users = set([])

                    for a in attachments:
                        author = a.getAuthor()
                        if author is not None:
                            users.add(author)
                    user_importer.importUsers(users)

                    for a in attachments:
                        print "Transfer attachment of " + issue.id + ": " + a.name
                        # TODO: add authorLogin to workaround http://youtrack.jetbrains.net/issue/JT-6082
                        a.authorLogin = target_login
                        try:
                            target.createAttachmentFromAttachment(issue.id, a)
                        except:
                            print("Cant import attachment [ %s ]" % a.name)

            except:
                print('Cant process issues from ' + str(start) + ' to ' + str(start + max))

            start += max

    print "Import issue links"
    link_importer.importCollectedLinks()


if __name__ == "__main__":
    main()
